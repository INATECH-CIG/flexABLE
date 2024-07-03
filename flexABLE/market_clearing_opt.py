
def marketClearing(self, t):
    # Initialize model
    model = pyo.ConcreteModel()

    # Extract bids and categorize them
    bidsReceived = {"Supply": [], "Demand": []}
    for b in self.bids:
        bidsReceived[b.bidType].append(b)

    # Add import and export bids
    bidsReceived["Supply"].append(Bid(issuer=self,
                                      ID="Bu{}t{}_import".format(self.name, t),
                                      price=-500.,
                                      amount=self.CBtrades['Import'][t],
                                      status="Sent",
                                      bidType="Supply"))
    
    bidsReceived["Demand"].append(Bid(issuer=self,
                                      ID="Bu{}t{}_export".format(self.name, t),
                                      price=2999.,
                                      amount=self.CBtrades['Export'][t],
                                      status="Sent",
                                      bidType="Demand"))

    # Inelastic demand bid
    bidsReceived["Demand"].append(Bid(issuer=self,
                                      ID="IEDt{}".format(t),
                                      price=3000.,
                                      amount=self.demand[t],
                                      status="Sent",
                                      bidType="InelasticDemand"))

    # Variables for supply and demand amounts
    model.supply_amounts = pyo.Var(range(len(bidsReceived["Supply"])), domain=pyo.NonNegativeReals)
    model.demand_amounts = pyo.Var(range(len(bidsReceived["Demand"])), domain=pyo.NonNegativeReals)

    # Objective function: minimize the difference between total supply and demand
    model.obj = pyo.Objective(expr=abs(sum(model.supply_amounts) - sum(model.demand_amounts)), sense=pyo.minimize)

    # Constraints
    def supply_constraint_rule(model, i):
        return model.supply_amounts[i] <= bidsReceived["Supply"][i].amount
    
    def demand_constraint_rule(model, i):
        return model.demand_amounts[i] <= bidsReceived["Demand"][i].amount

    model.supply_constraints = pyo.Constraint(range(len(bidsReceived["Supply"])), rule=supply_constraint_rule)
    model.demand_constraints = pyo.Constraint(range(len(bidsReceived["Demand"])), rule=demand_constraint_rule)

    # Solver
    solver = pyo.SolverFactory('glpk')
    solver.solve(model)

    # Process results
    confirmedBids = []
    for i in range(len(bidsReceived["Supply"])):
        if model.supply_amounts[i]() > 0:
            bidsReceived["Supply"][i].status = "Confirmed"
            confirmedBids.append(bidsReceived["Supply"][i])
    
    for i in range(len(bidsReceived["Demand"])):
        if model.demand_amounts[i]() > 0:
            bidsReceived["Demand"][i].status = "Confirmed"
            confirmedBids.append(bidsReceived["Demand"][i])

    # Assign confirmed bids to the class attribute
    self.confirmedBids = confirmedBids
