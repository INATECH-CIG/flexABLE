# -*- coding: utf-8 -*-
"""

@author: Nick_SimPC
"""

import torch as th
from torch.optim import Adam

import pickle
import os
import numpy as np

from policies import Actor
from misc import NormalActionNoise, initializer


class RLStorage():
    @initializer
    def __init__(self,
                 agent=None,
                 name='Storage_1',
                 technology='PSPP',
                 min_soc=1,
                 max_soc=1000,
                 max_power_ch=100,
                 max_power_dis=100,
                 efficiency_ch=0.8,
                 efficiency_dis=0.9,
                 ramp_up=100,
                 ramp_down=100,
                 variable_cost_ch=0.28,
                 variable_cost_dis=0.28,
                 natural_inflow=1.8,  # [MWh/qh]
                 company='UNIPER',
                 node='Bus_DE',
                 world=None,
                 **kwargs):


        #RL agent parameters
        self.obs_dim = self.world.obs_dim
        self.act_dim = self.world.act_dim
        self.learning_rate = self.world.learning_rate

        self.device = self.world.device
        self.float_type = self.world.float_type

        self.actor = Actor(self.obs_dim, self.act_dim, self.float_type).to(self.device)
        self.actor_target = Actor(self.obs_dim, self.act_dim, self.float_type).to(self.device)
        self.actor_target.load_state_dict(self.actor.state_dict())
        self.actor.optimizer = Adam(self.actor.parameters(), lr=self.learning_rate, eps=1e-04)

        if self.world.load_params:
            self.load_params(self.world.load_params)

        # Target networks should always be in eval mode
        self.actor_target.train(mode=False)

        self.action_noise = NormalActionNoise(mu=0., sigma=0.1, action_dimension=self.act_dim, scale=1., dt=1.)#dt=.999997)


    def reset(self):
        self.total_capacity = [0. for n in self.world.snapshots]
        self.scaled_total_capacity = np.array([0. for n in self.world.snapshots]).reshape(-1, 1)

        self.soc = [0. for n in self.world.snapshots]
        self.soc[0] = self.min_soc
        self.soc.append(self.min_soc)
        self.scaled_soc = np.array(self.soc).reshape(-1, 1)/self.max_soc

        self.energy_cost = [0. for n in self.world.snapshots]
        self.energy_cost.append(0.)
        self.scaled_energy_cost = np.array(self.energy_cost).reshape(-1, 1)

        self.bids_supply = {n:(0.,0.) for n in self.world.snapshots}
        self.bids_demand = {n:(0.,0.) for n in self.world.snapshots}

        self.sent_bids=[]

        self.rewards = [0. for _ in self.world.snapshots]
        self.profits = [0. for _ in self.world.snapshots]

        self.curr_obs = self.create_obs(0)
        self.next_obs = None

        self.curr_action = None
        self.curr_reward = None
        self.curr_experience = []


    def formulate_bids(self):
        """
        Take an action based on actor network, add exlorarion noise if needed

        Returns
        -------
            action (PyTorch Variable): Actions for this agent

        """
        if self.world.training:
            if self.world.episodes_done < self.world.learning_starts:
                self.curr_action = th.normal(0.0, 0.4, size=(1, self.act_dim), dtype=self.float_type).to(self.device).squeeze()
            else:
                self.curr_action = self.actor(self.curr_obs).detach()
                self.curr_action += th.tensor(self.action_noise.noise(), device=self.device, dtype=self.float_type)
        else:
            self.curr_action = self.actor(self.curr_obs).detach()

        return self.curr_action


    def step(self):
        t = self.world.currstep
        conf_bid_supply, conf_bid_demand = 0., 0.

        for bid in self.sent_bids:
            if 'supplyEOM' in bid.ID:
                conf_bid_supply = bid.confirmedAmount
                self.bids_supply[t] = (bid.confirmedAmount, bid.price)
            if 'demandEOM' in bid.ID:
                conf_bid_demand = bid.confirmedAmount
                self.bids_demand[t] = (bid.confirmedAmount, bid.price)

        self.total_capacity[t] = conf_bid_supply-conf_bid_demand
        self.scaled_total_capacity[t] = self.total_capacity[t]/self.max_power_ch

        self.soc[t+1] = self.soc[t] + (conf_bid_demand*self.efficiency_ch - conf_bid_supply/self.efficiency_dis)*self.world.dt
        self.soc[t+1] = max(self.soc[t+1], self.min_soc)
        self.scaled_soc[t+1] = self.soc[t+1]/self.max_soc

        if self.soc[t+1] >= self.min_soc+self.world.minBidEOM:
            self.energy_cost[t+1] = (self.energy_cost[t]*self.soc[t] - self.total_capacity[t]*self.world.mcp[t]*self.world.dt)/self.soc[t+1]
        else:
            self.energy_cost[t+1] = 0.

        self.energy_cost[t+1] = max(self.energy_cost[t+1], -100)
        self.energy_cost[t+1] = min(self.energy_cost[t+1], 100)
        self.scaled_energy_cost[t+1] = self.energy_cost[t+1]/100

        profit = (conf_bid_supply-conf_bid_demand)*self.world.mcp[t]*self.world.dt
        profit -= (conf_bid_supply*self.variable_cost_dis + conf_bid_demand*self.variable_cost_ch)
        
        scaling = 0.1/self.max_power_ch
        
        self.rewards[t] = profit*scaling
        self.profits[t] = profit

        if self.soc[t] == self.min_soc and self.curr_action[1] < 0:
            self.rewards[t] += 0.01
        elif self.soc[t] == self.max_soc and self.curr_action[1] >= 0:
            self.rewards[t] += 0.01

        self.curr_reward = self.rewards[t]
        self.next_obs = self.create_obs(t+1)
        self.curr_experience = [self.curr_obs,
                                self.next_obs,
                                self.curr_action,
                                self.curr_reward]

        self.curr_obs = self.next_obs

        self.sent_bids = []


    def feedback(self, bid):
        t = self.world.currstep

        if bid.status == "Confirmed":
            if 'CRMPosDem' in bid.ID:
                self.confQtyCRM_pos[t] = bid.confirmedAmount
                
            if 'CRMNegDem' in bid.ID:
                self.confQtyCRM_neg[t] = bid.confirmedAmount
            
        elif bid.status =="PartiallyConfirmed":
            if 'CRMPosDem' in bid.ID:
                self.confQtyCRM_pos[t] = bid.confirmedAmount
                
            if 'CRMNegDem' in bid.ID:
                self.confQtyCRM_neg[t] = bid.confirmedAmount
            
        self.sent_bids.append(bid)


    def create_obs(self, t):
        obs_len = 7
        obs = self.agent.obs.copy()

        # get the marginal cost
        if t < obs_len-1:
            obs.extend(self.scaled_soc[-obs_len+t+1:])
            obs.extend(self.scaled_soc[:t+1])
        else:
            obs.extend(self.scaled_soc[t-obs_len+1:t+1])

        obs.append(self.scaled_energy_cost[t])

        obs = np.array(obs)
        obs = th.tensor(obs, dtype=self.float_type).to(self.device, non_blocking=True).view(-1)

        return obs.detach().clone()


    def save_params(self, file_name='best_policy'):

        def save_obj(obj, directory):
            with open(directory + self.name + '.pkl', 'wb') as f:
                pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)

        obj = {'policy': self.actor.state_dict(),
               'target_policy': self.actor_target.state_dict(),
               'policy_optimizer': self.actor.optimizer.state_dict()}

        directory = 'output/' + self.world.simulation_id + '/policies/' + file_name + '/'

        if not os.path.exists(directory):
            os.makedirs(directory)

        save_obj(obj, directory)


    def load_params(self, load_params):
        if type(load_params) == dict:
            id = load_params['id']
            dir = load_params['dir']
        else:
            id = load_params
            dir='best_policy'

        def load_obj(directory):
            with open(directory + self.name + '.pkl', 'rb') as f:
                return pickle.load(f)

        directory = 'output/' + id + '/policies/' + dir + '/'

        if not os.path.exists(directory):
            raise FileNotFoundError('Specified directory for loading the actors policy does not exist!')

        params = load_obj(directory)

        self.actor.load_state_dict(params['policy'])
        self.actor_target.load_state_dict(params['target_policy'])
        self.actor.optimizer.load_state_dict(params['policy_optimizer'])


