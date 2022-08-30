# -*- coding: utf-8 -*-
"""
Created on Mon Oct 18 10:43:43 2021

@author: Nick_SimPC
"""

import numpy as np
from sklearn.preprocessing import MinMaxScaler, StandardScaler, MaxAbsScaler, RobustScaler
from functools import wraps
import inspect

class MeritOrder():
    def __init__(self, res_load, powerplants, snapshots):

        self.snapshots = snapshots
        self.res_load = list(res_load.values)
        self.powerplants = powerplants.copy()        
            
    def calculate_merit_order(self, res_load, t):
        powerplants = sorted(self.powerplants, key = lambda x, t = t: x.marginal_cost[t])        
        contractedSupply = 0
        
        if res_load <= 0:
            mcp = 0
        else:
            for pp in powerplants:                
                contractedSupply += pp.maxPower 
                mcp = pp.marginal_cost[t]
                if contractedSupply >= res_load:
                    break
            else:
                mcp = 100
                    
        return mcp
    
    
    def price_forward_curve(self):
        pfc = []
        for t in range(len(self.snapshots)):
            pfc.append(self.calculate_merit_order(self.res_load[t], t))
            
        return pfc


# from https://github.com/songrotek/DDPG/blob/master/ou_noise.py
class OUNoise():
    def __init__(self, action_dimension, mu=0, sigma=0.5, theta = 0.15, dt = 1e-2):
        self.action_dimension = action_dimension
        self.mu = mu
        self.theta = theta
        self.sigma = sigma
        self.dt = dt
        self.noise_prev = np.zeros(self.action_dimension)
        self.reset()

    def reset(self):
        self.noise_prev = self.initial_noise if self.initial_noise is not None else np.zeros(self.action_dimension)

    def noise(self):
        noise = (self.noise_prev + self.theta * (self.mu - self.noise_prev) * self.dt
        + self.sigma * np.sqrt(self.dt) * np.random.normal(size=self.action_dimension))
        self.noise_prev = noise

        return noise


class NormalActionNoise():
    def __init__(self, action_dimension, mu=0., sigma=0.1, scale = 1.0, dt = 0.9998):
        self.act_dimension = action_dimension
        self.mu = mu
        self.sigma = sigma
        self.scale = scale
        self.dt = dt

    def noise(self):
        noise = self.scale * np.random.normal(self.mu, self.sigma, self.act_dimension)
        self.scale = self.dt * self.scale #if self.scale >= 0.1 else self.scale
        return noise

    def reset(self):
        self.scale = 1.0


def initializer(func):
    """
    Automatically assigns the parameters.
    >>> class process:
    ...     @initializer
    ...     def __init__(self, cmd, reachable=False, user='root'):
    ...         pass
    >>> p = process('halt', True)
    >>> p.cmd, p.reachable, p.user
    ('halt', True, 'root')
    """
    names, varargs, keywords, defaults = inspect.getargspec(func)

    @wraps(func)
    def wrapper(self, *args, **kargs):
        
        for name, arg in list(zip(names[1:], args)) + list(kargs.items()):
            setattr(self, name, arg)
        
        for name, default in zip(reversed(names), reversed(defaults)):
            if not hasattr(self, name):
                setattr(self, name, default)

        func(self, *args, **kargs)

    return wrapper


def get_scaler(scaler):
    scalers = {
        "minmax": MinMaxScaler,
        "standard": StandardScaler,
        "maxabs": MaxAbsScaler,
        "robust": RobustScaler,
    }
    return scalers.get(scaler.lower())()

