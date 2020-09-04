# -*- coding: utf-8 -*-
"""
Created on Fri Sep  4 13:49:11 2020

@author: INATECH-XX
"""

"""
This is a small simple example showing how the redispatch logic works (negative power and marginal costs)
"""


import pypsa

network = pypsa.Network()

network.add('Bus','1')
network.add('Bus','2')

network.add('Load','L1', bus='1', p_set=1000)
network.add('Load','L2', bus='2', p_set=1000)

network.add('Generator','G1_1_pos', bus='1', p_nom=1000, marginal_cost=30, p_min_pu=0, p_max_pu=1)
network.add('Generator','G1_1_neg', bus='1', p_nom=1000, marginal_cost=-30, p_min_pu=-1, p_max_pu=0)
network.add('Generator','G1_2_pos', bus='1', p_nom=1000, marginal_cost=50, p_min_pu=0, p_max_pu=1)
network.add('Generator','G1_2_neg', bus='1', p_nom=1000, marginal_cost=-50, p_min_pu=-1, p_max_pu=0)
network.add('Generator','G1_fixed', bus='1', p_nom=1500, p_min_pu=1, p_max_pu=1)

network.add('Generator','G2_1_pos', bus='2', p_nom=1000, marginal_cost=30, p_min_pu=0, p_max_pu=1)
network.add('Generator','G2_1_neg', bus='2', p_nom=1000, marginal_cost=-30, p_min_pu=-1, p_max_pu=0)
network.add('Generator','G2_2_pos', bus='2', p_nom=1000, marginal_cost=50, p_min_pu=0, p_max_pu=1)
network.add('Generator','G2_2_neg', bus='2', p_nom=1000, marginal_cost=-50, p_min_pu=-1, p_max_pu=0)
network.add('Generator','G2_fixed', bus='2', p_nom=500, p_min_pu=1, p_max_pu=1)

network.add('Line', 'Line_Main', bus0='1', bus1='2', r=0.01,x=0.1, s_nom=0)

network.lopf()

print(network.generators_t.p.T)