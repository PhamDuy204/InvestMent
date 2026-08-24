# Model Escalation — V18

Current decision: **do not escalate complexity yet**.

The fixed chronological stack was not stably superior. The next rung is not RL or HPO; it is replay reconciliation. HistGB is the only nonlinear learner with positive mean timestamp IC and positive IC in 2/3 folds, but its magnitude is too small to justify parameter search.

If exact corrected replay later confirms a robust HistGB improvement, one fixed chronological stack re-test is allowed. Only after a predictive signal survives that stage may RL be evaluated as a bounded sizing/rebalancing/execution policy. Any RL reward must include transaction costs, turnover and risk, and exposure remains <=1x in simulation/paper only.
