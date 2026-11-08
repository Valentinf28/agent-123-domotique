"""Produce a per-device private technician recovery kit. Not a public customer label."""
import argparse
import json
import os
from pathlib import Path
from security import generate

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--machine-id',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();folder=Path(args.output);folder.mkdir(mode=0o700,parents=False,exist_ok=False)
    options,code=generate(args.machine_id)
    for name,value in [('options-private.json',json.dumps({'enabled':True,**options},indent=2)+'\n'),('technicien-prive.txt','MAINTENANCE INTERNE - NE PAS REMETTRE AU CLIENT\nMachine : '+args.machine_id+'\nAcces : Ctrl + Alt + F8\nCode : '+code+'\nSession maximale : 10 minutes\n')]:
        fd=os.open(folder/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(value);stream.flush();os.fsync(stream.fileno())
    print('Kit technicien prive cree. Conserver hors des sources et images communes.')
