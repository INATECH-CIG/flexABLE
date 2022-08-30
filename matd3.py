# -*- coding: utf-8 -*-
"""
Created on Thu Oct  7 15:43:00 2021

@author: Nick_SimPC
"""

import torch as th
from torch.optim import Adam
from torch.nn import functional as F

import pickle
import os

from policies import CriticTD3 as Critic
from buffer import ReplayBuffer

class TD3():
    def __init__(self,
                 env=None,
                 learning_rate=1e-4,
                 buffer_size=1e6,
                 learning_starts=100,
                 batch_size=1024,
                 tau=0.005,
                 gamma=0.99,
                 train_freq = 1,
                 gradient_steps=-1,
                 policy_delay=2,
                 target_policy_noise=0.2,
                 target_noise_clip=0.5):

        self.env = env
        self.learning_rate = learning_rate
        self.learning_starts = learning_starts
        self.batch_size = batch_size
        self.gamma = gamma
        self.tau = tau

        self.train_freq = len(env.snapshots) if train_freq == -1 else train_freq
        self.gradient_steps = self.train_freq if gradient_steps == -1 else gradient_steps
        self.policy_delay = policy_delay
        self.target_noise_clip = target_noise_clip
        self.target_policy_noise = target_policy_noise

        self.rl_agents = env.rl_powerplants+env.rl_storages
        self.n_rl_agents = len(self.rl_agents)

        self.obs_dim = env.obs_dim
        self.act_dim = env.act_dim

        self.device = env.device
        self.float_type = env.float_type
        
        self.buffer = ReplayBuffer(buffer_size = int(buffer_size),
                                   obs_dim = self.obs_dim,
                                   act_dim = self.act_dim,
                                   n_rl_agents = self.n_rl_agents,
                                   device=self.device)

        self.unique_obs_len = 8
        
        self.actors = [agent.actor for agent in self.rl_agents]
        self.actors_target = [agent.actor_target for agent in self.rl_agents]
        
        self.critics = [Critic(self.n_rl_agents, self.obs_dim, self.act_dim, self.float_type, self.unique_obs_len) for i in range(self.n_rl_agents)]
        self.critics_target = [Critic(self.n_rl_agents, self.obs_dim, self.act_dim, self.float_type, self.unique_obs_len) for i in range(self.n_rl_agents)]

        for x in self.critics:
            x = x.to(self.device)
            x.optimizer = Adam(x.parameters(), lr=self.learning_rate, eps=1e-03)
            
        for i, x in enumerate(self.critics_target):
            x.load_state_dict(self.critics[i].state_dict())
            x = x.to(self.device)
            # Target networks should always be in eval mode
            x.train(mode = False)

        if self.env.load_params:
            self.load_params(self.env.load_params)
            
        self.steps_done = 0
        self.n_updates = 0
        
        
    def update_policy(self):
        self.steps_done += 1

        if (self.steps_done % self.train_freq == 0) and (self.env.episodes_done+1 > self.learning_starts):
            
            self.set_training_mode(True)

            for _ in range(self.gradient_steps):
                self.n_updates += 1

                for i in range(self.n_rl_agents):
                    if i % 10 == 0:
                        #sample replay buffer
                        transitions = self.buffer.sample(self.batch_size)
                        states = transitions.observations
                        actions = transitions.actions
                        next_states = transitions.next_observations
                        rewards = transitions.rewards

                        with th.no_grad():
                            # Select action according to policy and add clipped noise
                            noise = actions.clone().data.normal_(0, self.target_policy_noise)
                            noise = noise.clamp(-self.target_noise_clip, self.target_noise_clip)

                            next_actions = [(actor_target(next_states[:, i, :]) + noise[:, i, :]).clamp(-1, 1) for i, actor_target in enumerate(self.actors_target)]
                            next_actions = th.stack(next_actions)

                            next_actions = (next_actions.transpose(0,1).contiguous())
                            next_actions = next_actions.view(-1, self.n_rl_agents * self.act_dim)
                        
                        all_actions = actions.view(self.batch_size, -1)

                    temp = th.cat((states[:, :i, self.obs_dim-self.unique_obs_len:].reshape(self.batch_size, -1),
                                   states[:, i+1:, self.obs_dim-self.unique_obs_len:].reshape(self.batch_size, -1)), axis=1)

                    all_states = th.cat((states[:, i, :].reshape(self.batch_size, -1), temp), axis = 1).view(self.batch_size, -1)

                    temp = th.cat((next_states[:, :i, self.obs_dim-self.unique_obs_len:].reshape(self.batch_size, -1),
                                   next_states[:, i+1:, self.obs_dim-self.unique_obs_len:].reshape(self.batch_size, -1)), axis=1)

                    all_next_states = th.cat((next_states[:, i, :].reshape(self.batch_size, -1), temp), axis = 1).view(self.batch_size, -1)

                    with th.no_grad():
                        # Compute the next Q-values: min over all critics targets
                        next_q_values = th.cat(self.critics_target[i](all_next_states, next_actions), dim = 1)
                        next_q_values, _ = th.min(next_q_values, dim = 1, keepdim=True)
                        target_Q_values = rewards[:, i].unsqueeze(1) + self.gamma * next_q_values

                    # Get current Q-values estimates for each critic network
                    current_Q_values = self.critics[i](all_states, all_actions)

                    # Compute critic loss
                    critic_loss = sum([F.mse_loss(current_q, target_Q_values) for current_q in current_Q_values])

                    # Optimize the critics
                    self.critics[i].optimizer.zero_grad()
                    critic_loss.backward()
                    self.critics[i].optimizer.step()

                    # Delayed policy updates
                    if self.n_updates % self.policy_delay == 0:
                        # Compute actor loss
                        state_i = states[:, i, :]
                        action_i = self.actors[i](state_i)

                        all_actions_clone = actions.clone()
                        all_actions_clone[:, i, :] = action_i
                        all_actions_clone = all_actions_clone.view(self.batch_size, -1)

                        actor_loss = -self.critics[i].q1_forward(all_states,all_actions_clone).mean()

                        # Optimize the actor
                        self.actors[i].optimizer.zero_grad()
                        actor_loss.backward()
                        self.actors[i].optimizer.step()

                        self.polyak_update(self.critics[i].parameters(), self.critics_target[i].parameters(), self.tau)
                        self.polyak_update(self.actors[i].parameters(), self.actors_target[i].parameters(), self.tau)

            self.set_training_mode(False)


    def polyak_update(params,target_params,tau):
        """
        Perform a Polyak average update on ``target_params`` using ``params``:
        target parameters are slowly updated towards the main parameters.
        ``tau``, the soft update coefficient controls the interpolation:
        ``tau=1`` corresponds to copying the parameters to the target ones whereas nothing happens when ``tau=0``.
        The Polyak update is done in place, with ``no_grad``, and therefore does not create intermediate tensors,
        or a computation graph, reducing memory cost and improving performance.  We scale the target params
        by ``1-tau`` (in-place), add the new weights, scaled by ``tau`` and store the result of the sum in the target
        params (in place).
        See https://github.com/DLR-RM/stable-baselines3/issues/93

        :param params: parameters to use to update the target params
        :param target_params: parameters to update
        :param tau: the soft update coefficient ("Polyak update", between 0 and 1)
        """
        with th.no_grad():
            # zip does not raise an exception if length of parameters does not match.
            for param, target_param in zip(params, target_params):
                target_param.data.mul_(1 - tau)
                th.add(target_param.data, param.data, alpha=tau, out=target_param.data)


    def set_training_mode(self, mode: bool) -> None:
        """
        Put the policy in either training or evaluation mode.

        This affects certain modules, such as batch normalisation and dropout.

        :param mode: if true, set to training mode, else set to evaluation mode
        """
        for x in self.critics:
            x = x.train(mode)

        for x in self.actors:
            x = x.train(mode)

        self.training = mode
    

    def save_params(self):
        
        def save_obj(obj, directory, agent):
            with open(directory + 'critic_' + str(agent) + '.pkl', 'wb') as f:
                pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)
                
        directory = 'output/' + self.env.simulation_id + '/policies/best_policy/'
        
        if not os.path.exists(directory):
            os.makedirs(directory)

        for i, agent in enumerate(self.rl_agents):
            obj = {'critic': self.critics[i].state_dict(),
                   'critic_target': self.critics_target[i].state_dict(),
                   'critic_optimizer': self.critics[i].optimizer.state_dict()}
            
            save_obj(obj, directory, agent.name)
        
    
    def load_params(self, load_params):
        if not load_params['load_critics']:
            return None

        if type(load_params) == dict:
            id = load_params['id']
            dir = load_params['dir']
        else:
            id = load_params
            dir='best_policy'
        
        self.env.logger.info('Loading critic parameters...')
        
        def load_obj(directory, agent):
            with open(directory + 'critic_' + str(agent) + '.pkl', 'rb') as f:
                return pickle.load(f)
        
        directory = 'output/' + id + '/policies/' + dir + '/'
        
        if not os.path.exists(directory):
            raise FileNotFoundError('Specified directory for loading the critics does not exist!')

        for i, agent in enumerate(self.rl_agents):
            params = load_obj(directory, agent.name)
            self.critics[i].load_state_dict(params['critic'])
            self.critics_target[i].load_state_dict(params['critic_target'])
            self.critics[i].optimizer.load_state_dict(params['critic_optimizer'])

            
        
        