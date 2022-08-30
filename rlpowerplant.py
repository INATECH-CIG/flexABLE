# -*- coding: utf-8 -*-
"""
Created on Mon Oct 18 09:46:19 2021

@author: Nick_SimPC
"""

import torch as th
from torch.optim import Adam

import pickle
import os
import numpy as np

from policies import Actor
from misc import NormalActionNoise, initializer


class RLPowerplant():
    @initializer
    def __init__(self,
                 agent=None,
                 name='KKW ISAR 2',
                 technology='nuclear',
                 fuel='uranium',
                 maxPower=1500,
                 minPower=600,
                 efficiency=0.3,
                 rampUp=890,
                 rampDown=890,
                 variableCosts=10.3,
                 hotStartCosts=140,
                 warmStartCosts=140,
                 coldStartCosts=140,
                 minOperatingTime=72,
                 minDowntime=10,
                 heatExtraction=False,
                 maxExtraction=0,
                 heatingDistrict='BW',
                 company='UNIPER',
                 year=1988,
                 node='Bus_DE',
                 world=None,
                 maxAvailability=None,
                 emission=None,
                 **kwargs):

        #power plant parameters
        self.minDowntime /= self.world.dt          # This was added to consider dt 15 mins
        self.minOperatingTime /= self.world.dt     # This was added to consider dt 15 mins
        self.crmTime = int(4 / self.world.dt)

        self.emission = self.world.emissionFactors[self.fuel] if self.emission is None else self.emission

        self.hotStartCosts *= self.maxPower
        self.warmStartCosts *= self.maxPower
        self.coldStartCosts *= self.maxPower

        self.marginal_cost = None
        self.scaled_marginal_cost = None

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

        self.action_noise = NormalActionNoise(mu=0., sigma=0.1, action_dimension=self.act_dim, scale=1., dt=1.)#dt=.999996)


    def reset(self):
        self.total_capacity = [0. for n in self.world.snapshots]
        self.total_capacity[-1] = self.minPower + (self.maxPower-self.minPower)/2

        self.total_scaled_capacity = np.array([0. for n in self.world.snapshots]).reshape(-1, 1)
        self.total_scaled_capacity[-1] = self.total_capacity[-1] / self.maxPower

        self.bids_mr = {n:(0.,0.) for n in self.world.snapshots}
        self.bids_flex = {n:(0.,0.) for n in self.world.snapshots}

        self.sentBids=[]

        self.current_downtime = 0

        self.curr_obs = self.create_obs(self.world.currstep)
        self.next_obs = None

        self.curr_action = None
        self.curr_reward = None
        self.curr_experience = []
        self.rewards = [0. for _ in self.world.snapshots]
        self.regrets = [0. for _ in self.world.snapshots]
        self.profits = [0. for _ in self.world.snapshots]


    def formulate_bids(self):
        """
        Take an action based on actor network, add exlorarion noise if needed

        Returns
        -------
            action (PyTorch Variable): Actions for this agent

        """
        if self.world.training:
            if self.world.episodes_done < self.world.learning_starts:
                self.curr_action = th.normal(0., 0.2, size=(1, self.act_dim), dtype=self.float_type).to(self.device).squeeze()
                self.curr_action += th.tensor(self.scaled_marginal_cost[self.world.currstep], device=self.device, dtype=self.float_type)
            else:
                self.curr_action = self.actor(self.curr_obs).detach()
                self.curr_action += th.tensor(self.action_noise.noise(), device=self.device, dtype=self.float_type)
        else:
            self.curr_action = self.actor(self.curr_obs).detach()

        return self.curr_action


    def step(self):
        t = self.world.currstep
        self.total_capacity[t] = 0

        for bid in self.sentBids:
            if 'mrEOM' in bid.ID or 'flexEOM' in bid.ID:
                self.total_capacity[t] += bid.confirmedAmount
                if 'mrEOM' in bid.ID:
                    self.bids_mr[t] = (bid.confirmedAmount, bid.price)
                else:
                    self.bids_flex[t] = (bid.confirmedAmount, bid.price)

        # Calculates market success
        if self.total_capacity[t] < self.minPower:
            self.total_capacity[t] = 0

        self.total_scaled_capacity[t] = self.total_capacity[t]/self.maxPower

        price_difference = self.world.mcp[t] - self.marginal_cost[t]
        profit = price_difference*self.total_capacity[t]*self.world.dt
        opportunity_cost = price_difference*(self.maxPower - self.total_capacity[t])*self.world.dt
        opportunity_cost = max(opportunity_cost, 0)

        self.profits[t] = profit
        self.regrets[t] = opportunity_cost

        scaling = 0.1/self.maxPower
        regret_scale = 0.2

        if self.total_capacity[t] != 0:
            if self.total_capacity[t-1] != 0:
                self.rewards[t] = (profit - regret_scale*opportunity_cost) * scaling
            else:
                self.rewards[t] = (profit - regret_scale*opportunity_cost - self.hotStartCosts/2) * scaling

        else:
            if self.total_capacity[t-1] != 0:
                self.rewards[t] = -(self.hotStartCosts/2 + regret_scale*opportunity_cost) * scaling
            else:
                self.rewards[t] = -regret_scale*opportunity_cost * scaling

        self.curr_reward = self.rewards[t]
        self.next_obs = self.create_obs(self.world.currstep+1)

        self.curr_experience = [self.curr_obs,
                                self.next_obs,
                                self.curr_action,
                                self.curr_reward]

        self.curr_obs = self.next_obs

        self.sentBids = []


    def feedback(self, bid):
        if bid.status == "Confirmed":
            if 'CRMPosDem' in bid.ID:
                self.confQtyCRM_pos.update(
                    {self.world.currstep+_: bid.confirmedAmount for _ in range(self.crmTime)})

            if 'CRMNegDem' in bid.ID:
                self.confQtyCRM_neg.update(
                    {self.world.currstep+_: bid.confirmedAmount for _ in range(self.crmTime)})

            if 'steam' in bid.ID:
                self.confQtyDHM_steam[self.world.currstep] = bid.confirmedAmount

        elif bid.status == "PartiallyConfirmed":
            if 'CRMPosDem' in bid.ID:
                self.confQtyCRM_pos.update(
                    {self.world.currstep+_: bid.confirmedAmount for _ in range(self.crmTime)})

            if 'CRMNegDem' in bid.ID:
                self.confQtyCRM_neg.update(
                    {self.world.currstep+_: bid.confirmedAmount for _ in range(self.crmTime)})

            if 'steam' in bid.ID:
                self.confQtyDHM_steam[self.world.currstep] = bid.confirmedAmount

        if 'steam' in bid.ID:
            self.powerLossFPP(self.world.currstep, bid)

        self.sentBids.append(bid)


    def create_obs(self, t):
        obs_len = 4
        obs = self.agent.obs.copy()

        # get the marginal cost
        if t < len(self.world.snapshots) - obs_len:
            obs.extend(self.scaled_marginal_cost[t:t+obs_len])
        else:
            obs.extend(self.scaled_marginal_cost[t:])
            obs.extend(self.scaled_marginal_cost[:obs_len-(len(self.world.snapshots)-t)])

        if t < obs_len:
            obs.extend(self.total_scaled_capacity[len(self.world.snapshots)-obs_len+t:])
            obs.extend(self.total_scaled_capacity[:t])
        else:
            obs.extend(self.total_scaled_capacity[t-obs_len:t])

        obs = np.array(obs)
        obs = th.tensor(obs, dtype=self.float_type).to(self.device, non_blocking=True).view(-1)

        return obs.detach().clone()


    def calculate_marginal_cost(self,
                               t,
                               efficiency_dependence=False,
                               passed_capacity=0):
        """
        Parameters
        ----------
        t : timestamp
            Defines the fuel price and CO2 prices at that timestep.
        efficiency_dependence : Bool
            DESCRIPTION.
        passed_capacity : float
            Specified the current power level, required to .

        Returns
        -------
        marginal_cost : TYPE
            DESCRIPTION.
        """

        fuel_price = self.world.fuelPrices[self.fuel][t]
        co2_price = self.world.fuelPrices['co2'][t]

        # Efficiency dependent marginal cost

        # Partial load efficiency dependent marginal costs
        if efficiency_dependence:
            if t > 0:
                if passed_capacity > 0:
                    current_capacity = passed_capacity
                elif self.total_capacity[t-1] >= self.minPower:
                    current_capacity = self.total_capacity[t-1]
                else:
                    current_capacity = self.maxPower
            else:
                current_capacity = self.maxPower

            capacity_ratio = current_capacity / self.maxPower

            if self.fuel in ['lignite', 'hard coal']:
                eta_loss = 0.095859 * (capacity_ratio ** 4) - 0.356010 * (capacity_ratio ** 3) \
                    + 0.532948 * (capacity_ratio ** 2) - \
                    0.447059 * capacity_ratio + 0.174262

            elif self.fuel == 'combined cycle gas turbine':
                eta_loss = 0.178749 * (capacity_ratio ** 4) - 0.653192 * (capacity_ratio ** 3) \
                    + 0.964704 * (capacity_ratio ** 2) - \
                    0.805845 * capacity_ratio + 0.315584

            elif self.fuel == 'open cycle gas turbine':
                eta_loss = 0.485049 * (capacity_ratio ** 4) - 1.540723 * (capacity_ratio ** 3) \
                    + 1.899607 * (capacity_ratio ** 2) - \
                    1.251502 * capacity_ratio + 0.407569

            else:
                eta_loss = 0

            marginal_cost = round(
                (fuel_price / (self.efficiency - eta_loss)) + (co2_price * (self.emission / (self.efficiency - eta_loss))) + self.variableCosts, 2)

        else:
            marginal_cost = (fuel_price / self.efficiency) + (co2_price *
                                                             (self.emission / self.efficiency)) + self.variableCosts

        return marginal_cost


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

