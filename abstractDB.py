# -*- coding: utf-8 -*-
"""
Created on Thu Sep 10 16:27:56 2020

@author: INATECH-XX
"""

from influxdb import InfluxDBClient

client = InfluxDBClient(host='localhost', port=8086)#, username='grafana', password='inatechadmin')

client.create_database('flexABLEx')

client.switch_database('flexABLEx')

json_body = [
    {
        "measurement": "PFC",
        "tags": {
            "user": "Nuclear",
        },
        "time": "2020-09-10T8:01:00Z",
        "fields": {
            "Power": 127
        }
    },
    {
        "measurement": "PFC",
        "tags": {
            "user": "Nuclear",
        },
        "time": "2020-09-10T8:04:00Z",
        "fields": {
            "Power": 132
        }
    },
    {
        "measurement": "PFC",
        "tags": {
            "user": "Nuclear",
        },
        "time": "2020-09-10T8:02:00Z",
        "fields": {
            "Power": 129
        }
    }
]

client.write_points(json_body)

    