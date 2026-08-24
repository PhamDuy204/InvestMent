# References — V18

1. Binance Public Data repository/documentation — official USD-M futures public klines are available as daily/monthly archives, with daily data published the following day.
2. Binance USD-M market-data API — historical funding-rate endpoint supports `startTime`, `endTime`, and chronological results without trading credentials.
3. scikit-learn `TimeSeriesSplit` documentation — time-ordered splitting is required when ordinary CV would train on future data and evaluate on past data; `gap` explicitly excludes samples between train and test.
4. Deep, Deep & Lamptey (2025), *Interpretable Hypothesis-Driven Trading: A Rigorous Walk-Forward Validation Framework for Market Microstructure Signals* — emphasizes strict information-set discipline, rolling OOS testing, realistic costs and constrained RL.
5. Zhang et al. (IJCAI 2023), *Towards Generalizable Reinforcement Learning for Trade Execution* — documents substantial overfitting risk in offline RL execution with limited contexts.
