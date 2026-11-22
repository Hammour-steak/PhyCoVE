# Elastic–fluid scenes

Scenes whose primary interaction is between an elastic body and a fluid. There are 4;
`../scene_registry.json` is authoritative and each scene's README gives its physics, cases,
requirements and the commands that rebuild it.

- [`bathroom_sink_duck_neospace`](bathroom_sink_duck_neospace/README.md): A faucet runs onto a rubber duck in a bathroom basin; the duck wobbles and deforms (Genesis MPM duck coupled to DFSPH water).
- [`elastic_fluid_duck`](elastic_fluid_duck/README.md): A rubber duck drops into an outdoor pool, deforms and returns to an upright floating pose (Genesis MPM duck coupled to DFSPH water).
- [`glass_bottle_water_balloon_true_coupled`](glass_bottle_water_balloon_true_coupled/README.md): A kitchen tap fills a blue balloon stretched over the mouth of a glass jar; the balloon swells inside and above the jar (XPBD membrane, hydrostatic water model).
- [`wind_flag`](wind_flag/README.md): A flag on a rooftop flagpole flutters in gusty wind (Genesis FEM and IPC shells under a prescribed wind force).
