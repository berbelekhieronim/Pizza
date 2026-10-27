# Examples (simulated data)

What the analysis reports look like before real data exists. **The data is made up**: 60 simulated participants
recruited through two links ("Group A/B (simulated)"), with randomly drawn "About you" answers, and a simulated
reference of 200 pizzas. No result in these files means anything.

| file | what |
|---|---|
| `dashboard.html` | the data preview: diet breakdown, normality against the reference, space / size / time by group, every participant |
| `explore.html` | ideas to test, leads, every measure screened across the study's groupings (neurotype, any neurodivergence, diagnosis status, eating history; gender, age and link group folded away), self-ratings, measure correlations, clusters × groups |
| `profiles.html` | every participant as a profile: clusters (when there is a clear structure), compare two clusters, the profile map and heatmap |
| `arrangement.html` | symmetry and contact drawn on each pizza |
| `methods.html` | how every number is counted, with worked examples |
| `simulate.py` | makes the simulated participants |

Open the HTML files in a browser. To rebuild them:

```
python3 simulate.py sample 5 60 AB
python3 simulate.py reference 9 200 B
python3 ../analysis/analyse.py sample/*.json --reference reference/*.json --out results
```
