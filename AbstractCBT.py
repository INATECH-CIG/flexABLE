# -*- coding: utf-8 -*-
"""
Created on Wed Sep  9 10:02:49 2020

@author: INATECH-XX
"""

"""
This is a small simple example showing how the cross border transfers from german point of view could be simplified
"""


import pypsa

network = pypsa.Network()
network.set_snapshots(range(5))
network.add('Bus','1')
network.add('Bus','2')

network.add('Load',
            'L1',
            bus='1',
            p_set=[1000,1000,1500,1200,1000])

network.add('Generator','G1',
            bus='1',
            p_nom=1500,
            marginal_cost=[30,15,30,10,30], 
            p_min_pu=[0,0,0,1,0], 
            p_max_pu=[1,0.5,1,1,1])

network.add('Generator',
            'Export',
            bus='2',
            p_nom=1500,
            p_min_pu=0,
            p_max_pu=1,
            marginal_cost=[300,300,300,300,300])
network.add('Generator',
            'Import',
            bus='2',
            p_nom=1500,
            p_min_pu=0,
            p_max_pu=1,
            sign=-1,
            marginal_cost=[300,300,300,300,300])


network.add('Line', 'Line_Main', bus0='1', bus1='2', r=0.01,x=0.1, s_nom=300)

network.lopf(solver_name='gurobi')

print(network.generators_t.p.T)