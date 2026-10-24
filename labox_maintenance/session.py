"""Authentication before every native HAOS session. No network listener."""
import json
import time
from pathlib import Path
from security import Attempts,Refused,valid_configuration,verify

class Session:
    def __init__(self,options,host,attempts):self.options=options;self.host=host;self.attempts=attempts
    async def open(self,code,return_vt=1,before_start=None):
        valid_configuration(self.options,await self.host.machine_id())
        if self.attempts.remaining():raise Refused('attendre_avant_nouvel_essai')
        if not verify(self.options,code):
            self.attempts.failed();raise Refused('code_incorrect')
        if before_start:before_start()
        await self.host.start(return_vt)
        self.attempts.succeeded()
        return {'sessionStarted':True,'maximumSeconds':600}
