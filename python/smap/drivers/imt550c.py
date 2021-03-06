"""
Copyright (c) 2011, 2012, Regents of the University of California
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions 
are met:

 - Redistributions of source code must retain the above copyright
   notice, this list of conditions and the following disclaimer.
 - Redistributions in binary form must reproduce the above copyright
   notice, this list of conditions and the following disclaimer in the
   documentation and/or other materials provided with the
   distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS 
FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL 
THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, 
INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES 
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR 
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) 
HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, 
STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) 
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED 
OF THE POSSIBILITY OF SUCH DAMAGE.
"""
"""
@author Jonathan Fuerst <jonf@itu.dk>
"""
import os, requests, __builtin__
from smap import actuate, driver
from smap.util import periodicSequentialCall
from smap.contrib import dtutil
from requests.auth import HTTPDigestAuth
import json
import time

from twisted.internet import threads

class IMT550C(driver.SmapDriver):
    def setup(self, opts):
        self.tz = opts.get('Metadata/Timezone', None)
        self.rate = float(opts.get('Rate', 1))
        self.ip = opts.get('ip', None)
        self.user = opts.get('user', None)
        self.password = opts.get('password', None)
        self.points0 = [
                          {"name": "temp", "unit": "F", "data_type": "double",
                            "OID": "4.1.13", "range": (-200,2000), "access": 4,
                            "act_type": None}, # thermAverageTemp
                          {"name": "tmode", "unit": "Mode", "data_type": "long",
                            "OID": "4.1.1", "range": (1,2,3,4), "access": 6,
                            "act_type": "discrete"}, # thermHvacMode
                          {"name": "fmode", "unit": "Mode", "data_type": "long",
                            "OID": "4.1.3", "range": (1,2,3), "access": 6,
                            "act_type": "discrete"}, # thermFanMode
                          {"name": "thermSetbackStatus", "unit": "Mode",
                            "data_type": "long", "OID": "4.1.9",
                            "range": (1,2,3), "access": 6,
                            "act_type": "discrete"}, # hold/override
                          {"name": "t_heat", "unit": "F", "data_type": "double",
                            "OID": "4.1.5", "range": (450,950), "access": 6,
                            "act_type": "continuous"}, #thermSetbackHeat
                          {"name": "t_cool", "unit": "F", "data_type": "double",
                            "OID": "4.1.6", "range": (450,950), "access": 6,
                            "act_type": "continuous"}, #thermSetbackCool
                          {"name": "thermConfigHumidityCool", "unit": "%RH",
                            "data_type": "double", "OID": "4.2.22",
                            "range": (0,95), "access": 0,
                            "act_type": "continuous"}
                          #TODO needs better support in smap
                          #(continous and discrete and only inetgers, 0, 5-95)
                       ]
        for p in self.points0:
          self.add_timeseries('/' + p["name"], p["unit"],
              data_type=p["data_type"], timezone=self.tz)
          if p['access'] == 6:
            if p['act_type'] == 'binary':
              print "not implemented"
            elif p['act_type'] == 'discrete':
              klass = DiscreteActuator
              setup={'model': 'discrete', 'ip':self.ip, 'states': p['range'],
                  'user': self.user, 'password': self.password, 'OID': p['OID']}
              self.add_actuator('/' + p['name'] + '_act', p['unit'], klass,
                  setup=setup, data_type = p['data_type'], write_limit=5)
            elif p['act_type'] == 'continuous':
              klass = ContinuousActuator
              setup={'model': 'continuous', 'ip':self.ip, 'range': p['range'],
                  'user': self.user, 'password': self.password, 'OID': p['OID']}
              self.add_actuator('/' + p['name'] + '_act', p['unit'], klass,
                  setup=setup, data_type = p['data_type'], write_limit=5)

    def start(self):
        # call self.read every self.rate seconds
        periodicSequentialCall(self.read).start(self.rate)

    def read(self):
        url = 'http://' + self.ip + "/get"
        for p in self.points0:
          r = requests.get(url, auth=HTTPDigestAuth(self.user, self.password),
              params="OID"+p["OID"])
          val = r.text.split('=', 1)[-1]
          if p["data_type"] == "long":
            self.add("/" + p["name"], long(val))
            #data_type = p["data_type"]
            #data_type_f = getattr(__builtin__, data_type)
            #val = data_type_f(val)
          else:
            self.add("/" + p["name"], float(val))

class ThermoActuator(actuate.SmapActuator):

    def setup(self, opts):
        self.ip = opts['ip']
        self.user = opts['user']
        self.password = opts['password']
        self.url = 'http://' + self.ip
        self.OID = opts['OID']

    def get_state(self, request):
        r = requests.get(self.url+"/get?OID"+self.OID+"=",
            auth=HTTPDigestAuth(self.user, self.password))
        rv = (r.text.split('=', 1)[-1])
        return self.parse_state(rv)

    def set_state(self, request, state):
        payload = {"OID"+self.OID: int(state), "submit": "Submit"}
        r = requests.get('http://'+self.ip+"/pdp/",
            auth=HTTPDigestAuth('admin', 'admin'), params=payload)
        return state

class BinaryActuator(ThermoActuator, actuate.BinaryActuator):
    def setup(self, opts):
        actuate.BinaryActuator.setup(self, opts)
        ThermoActuator.setup(self, opts)

class DiscreteActuator(ThermoActuator, actuate.NStateActuator):
    def setup(self, opts):
        actuate.NStateActuator.setup(self, opts)
        ThermoActuator.setup(self, opts)

class ContinuousActuator(ThermoActuator, actuate.ContinuousActuator):
    def setup(self, opts):
        actuate.ContinuousActuator.setup(self, opts)
        ThermoActuator.setup(self, opts)
