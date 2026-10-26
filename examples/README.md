# Examples (simulated data)

What the analysis reports look like before real data exists. **The data is made up**: 60 simulated participants in
two groups ("Group A/B (simulated)") and a simulated reference of 200 pizzas. No result in these files means anything.

| file | what |
|---|---|
| `dashboard.html` | the data preview: diet breakdown, normality against the reference, space / size / time by group, every participant |
| `profiles.html` | every participant as a profile: compare any two, clusters, the profile map and heatmap |
| `arrangement.html` | symmetry and contact drawn on each pizza (from a smaller set of 16 deliberately varied simulated pizzas) |
| `simulate.py` | makes the simulated participants |

Open the HTML files in a browser. To rebuild them:

```
python3 simulate.py sample 5 60 AB
python3 simulate.py reference 9 200 B
python3 ../analysis/analyse.py sample/*.json --reference reference/*.json --group group --out results
```
