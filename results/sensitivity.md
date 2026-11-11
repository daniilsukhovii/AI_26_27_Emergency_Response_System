# Sensitivity analysis

Baseline: planner=csp, tau=0.5, after_job=on-site, congested_multiplier=1.5, traffic_multipliers=Low=1,Medium=1.2,High=1.5, unobserved_traffic=initial, hmm_init=pi_is_t1, csp_node_limit=200000, validate=yes, use_bayes=yes, use_hmm=yes

| scenario | planner | varied factor | value | handled | avg response (s) [self] | % met [self] | % Critical met [self] | removed roads | observed traffic / usable roads | CSP nodes | CSP optimal | errors [baseline] | avg response (s) [baseline] | % met [baseline] | % Critical met [baseline] |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Scenario1 | csp | baseline | - | 7/7 | 107.4 | 71.4 | 100.0 | 4 | 10 / 10 | 8 | yes | - | 107.4 | 71.4 | 100.0 |
| Scenario1 | csp | tau | 0.3 | 7/7 | 107.4 | 71.4 | 100.0 | 4 | 10 / 10 | 8 | yes | - | 107.4 | 71.4 | 100.0 |
| Scenario1 | csp | tau | 0.7 | 7/7 | 104.9 | 71.4 | 100.0 | 2 | 12 / 12 | 8 | yes | E304 x1 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario1 | csp | unobserved_traffic | neutral | 7/7 | 107.4 | 71.4 | 100.0 | 4 | 10 / 10 | 8 | yes | - | 107.4 | 71.4 | 100.0 |
| Scenario1 | csp | unobserved_traffic | stationary | 7/7 | 107.4 | 71.4 | 100.0 | 4 | 10 / 10 | 8 | yes | - | 107.4 | 71.4 | 100.0 |
| Scenario1 | csp | after_job | return | 7/7 | 123.4 | 71.4 | 100.0 | 4 | 10 / 10 | 7 | yes | - | 123.4 | 71.4 | 100.0 |
| Scenario1 | csp | use_bayes | False | 7/7 | 70.2 | 100.0 | 100.0 | 0 | 14 / 14 | 6 | yes | E304 x4, E404 x1 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario1 | csp | use_hmm | False | 7/7 | 99.8 | 85.7 | 100.0 | 4 | 10 / 10 | 8 | yes | E404 x3 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario1 | csp | use_bayes+use_hmm | False | 7/7 | 67.3 | 100.0 | 100.0 | 0 | 14 / 14 | 6 | yes | E304 x4, E404 x1 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario1 | greedy | baseline | - | 7/7 | 107.6 | 71.4 | 100.0 | 4 | 10 / 10 | - | - | - | 107.6 | 71.4 | 100.0 |
| Scenario1 | greedy | tau | 0.3 | 7/7 | 107.6 | 71.4 | 100.0 | 4 | 10 / 10 | - | - | - | 107.6 | 71.4 | 100.0 |
| Scenario1 | greedy | tau | 0.7 | 7/7 | 105.1 | 71.4 | 100.0 | 2 | 12 / 12 | - | - | E304 x1 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario1 | greedy | unobserved_traffic | neutral | 7/7 | 107.6 | 71.4 | 100.0 | 4 | 10 / 10 | - | - | - | 107.6 | 71.4 | 100.0 |
| Scenario1 | greedy | unobserved_traffic | stationary | 7/7 | 107.6 | 71.4 | 100.0 | 4 | 10 / 10 | - | - | - | 107.6 | 71.4 | 100.0 |
| Scenario1 | greedy | after_job | return | 7/7 | 123.4 | 71.4 | 100.0 | 4 | 10 / 10 | - | - | - | 123.4 | 71.4 | 100.0 |
| Scenario1 | greedy | use_bayes | False | 7/7 | 70.2 | 100.0 | 100.0 | 0 | 14 / 14 | - | - | E304 x4, E404 x1 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario1 | greedy | use_hmm | False | 7/7 | 102.3 | 71.4 | 100.0 | 4 | 10 / 10 | - | - | E404 x3 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario1 | greedy | use_bayes+use_hmm | False | 7/7 | 67.3 | 100.0 | 100.0 | 0 | 14 / 14 | - | - | E304 x4, E404 x1 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario2 | csp | baseline | - | 12/12 | 39.1 | 58.3 | 50.0 | 2 | 3 / 28 | 10 | yes | - | 39.1 | 58.3 | 50.0 |
| Scenario2 | csp | tau | 0.3 | 12/12 | 39.1 | 58.3 | 50.0 | 2 | 3 / 28 | 10 | yes | - | 39.1 | 58.3 | 50.0 |
| Scenario2 | csp | tau | 0.7 | 12/12 | 39.1 | 58.3 | 50.0 | 2 | 3 / 28 | 10 | yes | - | 39.1 | 58.3 | 50.0 |
| Scenario2 | csp | unobserved_traffic | neutral | 12/12 | 34.7 | 91.7 | 100.0 | 2 | 3 / 28 | 10 | yes | E404 x2 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario2 | csp | unobserved_traffic | stationary | 12/12 | 41.4 | 33.3 | 16.7 | 2 | 3 / 28 | 10 | yes | - | 39.7 | 58.3 | 50.0 |
| Scenario2 | csp | after_job | return | 12/12 | 46.0 | 50.0 | 50.0 | 2 | 3 / 28 | 6 | yes | - | 46.0 | 50.0 | 50.0 |
| Scenario2 | csp | use_bayes | False | 12/12 | 32.0 | 91.7 | 100.0 | 0 | 3 / 30 | 7 | yes | E404 x1 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario2 | csp | use_hmm | False | 12/12 | 32.5 | 91.7 | 100.0 | 2 | 3 / 28 | 10 | yes | E404 x2 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario2 | csp | use_bayes+use_hmm | False | 12/12 | 27.0 | 100.0 | 100.0 | 0 | 3 / 30 | 8 | yes | E404 x2 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario2 | greedy | baseline | - | 12/12 | 39.3 | 58.3 | 50.0 | 2 | 3 / 28 | - | - | - | 39.3 | 58.3 | 50.0 |
| Scenario2 | greedy | tau | 0.3 | 12/12 | 39.3 | 58.3 | 50.0 | 2 | 3 / 28 | - | - | - | 39.3 | 58.3 | 50.0 |
| Scenario2 | greedy | tau | 0.7 | 12/12 | 39.3 | 58.3 | 50.0 | 2 | 3 / 28 | - | - | - | 39.3 | 58.3 | 50.0 |
| Scenario2 | greedy | unobserved_traffic | neutral | 12/12 | 35.0 | 83.3 | 100.0 | 2 | 3 / 28 | - | - | E404 x1 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario2 | greedy | unobserved_traffic | stationary | 12/12 | 41.5 | 33.3 | 16.7 | 2 | 3 / 28 | - | - | - | 39.6 | 58.3 | 50.0 |
| Scenario2 | greedy | after_job | return | 12/12 | 46.0 | 50.0 | 50.0 | 2 | 3 / 28 | - | - | - | 46.0 | 50.0 | 50.0 |
| Scenario2 | greedy | use_bayes | False | 12/12 | 32.8 | 91.7 | 100.0 | 0 | 3 / 30 | - | - | E304 x1, E404 x1 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario2 | greedy | use_hmm | False | 12/12 | 32.8 | 83.3 | 100.0 | 2 | 3 / 28 | - | - | E404 x1 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario2 | greedy | use_bayes+use_hmm | False | 12/12 | 30.7 | 83.3 | 100.0 | 0 | 3 / 30 | - | - | E304 x2, E404 x1 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario3 | csp | baseline | - | 20/20 | 1430.5 | 50.0 | 50.0 | 2 | 10 / 58 | 31 | yes | - | 1430.5 | 50.0 | 50.0 |
| Scenario3 | csp | tau | 0.3 | 20/20 | 1430.5 | 50.0 | 50.0 | 2 | 10 / 58 | 31 | yes | - | 1430.5 | 50.0 | 50.0 |
| Scenario3 | csp | tau | 0.7 | 20/20 | 1456.6 | 50.0 | 50.0 | 0 | 10 / 60 | 22 | yes | E304 x3 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario3 | csp | unobserved_traffic | neutral | 20/20 | 1308.3 | 65.0 | 62.5 | 2 | 10 / 58 | 30 | yes | E404 x5 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario3 | csp | unobserved_traffic | stationary | 20/20 | 1544.4 | 45.0 | 50.0 | 2 | 10 / 58 | 28 | yes | - | 1457.1 | 50.0 | 50.0 |
| Scenario3 | csp | after_job | return | 20/20 | 1996.1 | 40.0 | 25.0 | 2 | 10 / 58 | 40 | yes | - | 1996.1 | 40.0 | 25.0 |
| Scenario3 | csp | use_bayes | False | 20/20 | 1209.0 | 65.0 | 62.5 | 0 | 10 / 60 | 22 | yes | E304 x4, E404 x2 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario3 | csp | use_hmm | False | 20/20 | 1271.7 | 65.0 | 62.5 | 2 | 10 / 58 | 30 | yes | E404 x5 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario3 | csp | use_bayes+use_hmm | False | 20/20 | 1041.0 | 90.0 | 87.5 | 0 | 10 / 60 | 15 | yes | E304 x4, E404 x3 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario3 | greedy | baseline | - | 20/20 | 1547.9 | 45.0 | 50.0 | 2 | 10 / 58 | - | - | - | 1547.9 | 45.0 | 50.0 |
| Scenario3 | greedy | tau | 0.3 | 20/20 | 1547.9 | 45.0 | 50.0 | 2 | 10 / 58 | - | - | - | 1547.9 | 45.0 | 50.0 |
| Scenario3 | greedy | tau | 0.7 | 20/20 | 1427.7 | 45.0 | 50.0 | 0 | 10 / 60 | - | - | E304 x3 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario3 | greedy | unobserved_traffic | neutral | 20/20 | 1417.6 | 60.0 | 62.5 | 2 | 10 / 58 | - | - | E404 x1 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario3 | greedy | unobserved_traffic | stationary | 20/20 | 1662.9 | 40.0 | 50.0 | 2 | 10 / 58 | - | - | - | 1554.9 | 45.0 | 50.0 |
| Scenario3 | greedy | after_job | return | 20/20 | 2349.3 | 25.0 | 12.5 | 2 | 10 / 58 | - | - | - | 2349.3 | 25.0 | 12.5 |
| Scenario3 | greedy | use_bayes | False | 20/20 | 1210.4 | 70.0 | 62.5 | 0 | 10 / 60 | - | - | E304 x3, E404 x1 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario3 | greedy | use_hmm | False | 20/20 | 1378.6 | 60.0 | 62.5 | 2 | 10 / 58 | - | - | E404 x1 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
| Scenario3 | greedy | use_bayes+use_hmm | False | 20/20 | 1070.9 | 100.0 | 100.0 | 0 | 10 / 60 | - | - | E304 x3 | n/a (infeasible) | n/a (infeasible) | n/a (infeasible) |
