# -*- coding: utf-8 -*-
"""
Created on Thu Oct  7 12:04:23 2021

@author: Nick_SimPC
"""

import torch as th
from torch import nn
import torch.nn.functional as F


class CriticTD3(nn.Module):
    """Initialize parameters and build model.
        Args:
            n_agents (int): Number of agents
            obs_dim (int): Dimension of each state
            act_dim (int): Dimension of each action
        Return:
            value output of network 
    """
    
    def __init__(self, n_agents, obs_dim, act_dim, float_type, unique_obs_len=16):
        super(CriticTD3, self).__init__()

        self.obs_dim = obs_dim + unique_obs_len*(n_agents-1)
        self.act_dim = act_dim * n_agents

        # Q1 architecture
        if n_agents <= 50:
            self.FC1_1 = nn.Linear(self.obs_dim + self.act_dim, 512, dtype = float_type)
            self.FC1_2 = nn.Linear(512, 256, dtype = float_type)
            self.FC1_3 = nn.Linear(256, 128, dtype = float_type)
            self.FC1_4 = nn.Linear(128, 1, dtype = float_type)
        else:
            self.FC1_1 = nn.Linear(self.obs_dim + self.act_dim, 1024, dtype = float_type)
            self.FC1_2 = nn.Linear(1024, 512, dtype = float_type)
            self.FC1_3 = nn.Linear(512, 128, dtype = float_type)
            self.FC1_4 = nn.Linear(128, 1, dtype = float_type)

        # Q2 architecture
        if n_agents <= 50:
            self.FC2_1 = nn.Linear(self.obs_dim + self.act_dim, 512, dtype = float_type)
            self.FC2_2 = nn.Linear(512, 256, dtype = float_type)
            self.FC2_3 = nn.Linear(256, 128, dtype = float_type)
            self.FC2_4 = nn.Linear(128, 1, dtype = float_type)
        else:
            self.FC2_1 = nn.Linear(self.obs_dim + self.act_dim, 1024, dtype = float_type)
            self.FC2_2 = nn.Linear(1024, 512, dtype = float_type)
            self.FC2_3 = nn.Linear(512, 128, dtype = float_type)
            self.FC2_4 = nn.Linear(128, 1, dtype = float_type)


    def forward(self, obs, actions):
        xu = th.cat([obs, actions], 1)
        
        x1 = F.relu(self.FC1_1(xu))
        x1 = F.relu(self.FC1_2(x1))
        x1 = F.relu(self.FC1_3(x1))
        x1 = self.FC1_4(x1)

        x2 = F.relu(self.FC2_1(xu))
        x2 = F.relu(self.FC2_2(x2))
        x2 = F.relu(self.FC2_3(x2))
        x2 = self.FC2_4(x2)
        
        return x1, x2


    def q1_forward(self, obs, actions):
        """
        Only predict the Q-value using the first network.
        This allows to reduce computation when all the estimates are not needed
        (e.g. when updating the policy in TD3).
        """
        x = th.cat([obs, actions], 1)
        x = F.relu(self.FC1_1(x))
        x = F.relu(self.FC1_2(x))
        x = F.relu(self.FC1_3(x))
        x = self.FC1_4(x)

        return x


class Actor(nn.Module):
    def __init__(self, obs_dim, act_dim, float_type):
        super(Actor, self).__init__()
        
        self.FC1 = nn.Linear(obs_dim, 256, dtype = float_type)
        self.FC2 = nn.Linear(256, 128, dtype = float_type)
        self.FC3 = nn.Linear(128, act_dim, dtype = float_type)
        

    def forward(self, obs):
        x = F.relu(self.FC1(obs))
        x = F.relu(self.FC2(x))
        x = th.tanh(self.FC3(x))
        
        return x