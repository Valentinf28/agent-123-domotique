"""DHCP/DNS and firewall restricted to the selected AP interface. No host file edits."""
import subprocess
import re
from model import IP, PORT, Refused

class AccessPoint:
    def __init__(self, interface):
        if not re.fullmatch('[A-Za-z0-9_.:-]{1,15}', interface): raise Refused('interface_invalide')
        self.interface = interface; self.dns = None
        self.chain = 'LABOX_SETUP'

    def run(self, binary, args, *, check=True):
        return subprocess.run([binary, '-w', '3', *args], check=check,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def firewall(self):
        # Build private chains before attaching. Existing HA/Docker rules are never flushed.
        for binary in ('iptables', 'ip6tables'):
            self.run(binary, ['-N', self.chain], check=False)
            self.run(binary, ['-F', self.chain])
        self.run('iptables', ['-A', self.chain, '-m', 'conntrack', '--ctstate', 'ESTABLISHED,RELATED', '-j', 'ACCEPT'])
        self.run('iptables', ['-A', self.chain, '-p', 'udp', '--dport', '67:68', '-j', 'ACCEPT'])
        for protocol, port in [('udp', '53'), ('tcp', '53'), ('tcp', str(PORT))]:
            self.run('iptables', ['-A', self.chain, '-d', IP, '-p', protocol, '--dport', port, '-j', 'ACCEPT'])
        self.run('iptables', ['-A', self.chain, '-j', 'DROP'])
        self.run('ip6tables', ['-A', self.chain, '-j', 'DROP'])
        for binary in ('iptables', 'ip6tables'):
            for chain in ('INPUT', 'FORWARD'):
                rule = ['-i', self.interface, '-j', self.chain] if chain == 'INPUT' else ['-i', self.interface, '-j', 'DROP']
                if self.run(binary, ['-C', chain, *rule], check=False).returncode:
                    self.run(binary, ['-I', chain, '1', *rule])
        # Redirect only AP HTTP; HTTPS is never intercepted.
        rule = ['-i', self.interface, '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-ports', str(PORT)]
        if self.run('iptables', ['-t', 'nat', '-C', 'PREROUTING', *rule], check=False).returncode:
            self.run('iptables', ['-t', 'nat', '-I', 'PREROUTING', '1', *rule])

    def start_dns(self):
        self.dns = subprocess.Popen(['dnsmasq', '--keep-in-foreground', '--conf-file=/dev/null',
            '--bind-interfaces', '--interface=' + self.interface, '--listen-address=' + IP,
            '--except-interface=lo', '--no-resolv', '--no-hosts', '--address=/#/' + IP,
            '--dhcp-range=192.168.77.20,192.168.77.80,255.255.255.0,5m',
            '--dhcp-option=3,' + IP, '--dhcp-option=6,' + IP,
            '--dhcp-leasefile=/tmp/labox-setup.leases', '--dhcp-authoritative',
            '--log-facility=/dev/null', '--pid-file='], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def healthy(self): return self.dns is not None and self.dns.poll() is None

    def stop(self):
        if self.dns:
            self.dns.terminate()
            try: self.dns.wait(timeout=3)
            except subprocess.TimeoutExpired: self.dns.kill(); self.dns.wait()
            self.dns = None
        for binary in ('iptables', 'ip6tables'):
            for chain in ('INPUT', 'FORWARD'):
                rule = ['-i', self.interface, '-j', self.chain] if chain == 'INPUT' else ['-i', self.interface, '-j', 'DROP']
                self.run(binary, ['-D', chain, *rule], check=False)
            self.run(binary, ['-F', self.chain], check=False)
            self.run(binary, ['-X', self.chain], check=False)
        self.run('iptables', ['-t', 'nat', '-D', 'PREROUTING', '-i', self.interface,
            '-p', 'tcp', '--dport', '80', '-j', 'REDIRECT', '--to-ports', str(PORT)], check=False)
