# Rigid–elastic scenes

Scenes whose primary interaction is between a rigid body and a deformable solid (elastic, elastoplastic or cloth). There are 28;
`../scene_registry.json` is authoritative and each scene's README gives its physics, cases,
requirements and the commands that rebuild it.

- [`beach_ball_hammock_mpm`](beach_ball_hammock_mpm/README.md): A beach ball drops into an elastic hammock strung between two posts and settles (Taichi MLS-MPM hammock, rigid ball).
- [`book_pillow_bedroom`](book_pillow_bedroom/README.md): A blue book drops onto a bed pillow, pressing the pillow and the duvet beneath it down.
- [`cabinet_towel_pinch`](cabinet_towel_pinch/README.md): A closing kitchen cabinet door catches the cotton hand towel draped over its top edge.
- [`curtain_doraemon_drape`](curtain_doraemon_drape/README.md): A short linen curtain falls onto a porcelain vase on a window-side desk and drapes over it.
- [`egg_dough`](egg_dough/README.md): A brown egg drops off-centre onto kneaded dough, sinks in, tips over and settles in the dent (Taichi viscoelastic FEM).
- [`elastic_key_strap`](elastic_key_strap/README.md): Keys hanging on a thin silicone strap from a wall rack drop, stretch the strap and bounce.
- [`football_goal_net`](football_goal_net/README.md): A football is struck into the goal, hits the back net and is thrown back out onto the pitch.
- [`gym_landing_mat`](gym_landing_mat/README.md): A medicine ball drops at a slant onto a gym landing mat, which is pressed in and springs back.
- [`metal_pendulum_horizontal_spring`](metal_pendulum_horizontal_spring/README.md): A steel pendulum ball hits the plate of a horizontal guided coil spring, compresses it and is pushed back (MuJoCo).
- [`metro_security_bag_curtain`](metro_security_bag_curtain/README.md): A backpack on an X-ray scanner belt pushes through the lead exit curtain, slides down a chute and stops.
- [`passive_car_spring_return_ramp`](passive_car_spring_return_ramp/README.md): An unpowered toy SUV rolls down a ramp into a spring-backed bumper and is pushed back up the ramp (MuJoCo).
- [`phone_sofa_drop`](phone_sofa_drop/README.md): A phone drops onto a soft sofa cushion, dents it, bounces and comes to rest (libuipc rigid phone, FEM cushion).
- [`picnic_ground_blanket`](picnic_ground_blanket/README.md): A mandarin orange rolls across a gingham picnic blanket on a lawn, pressing a shallow dip into it.
- [`plastic_ruler_coin`](plastic_ruler_coin/README.md): A coin drops onto the overhanging end of a plastic ruler held down by a book; the ruler bends and rings down.
- [`rubber_band_wood_slider`](rubber_band_wood_slider/README.md): A stretched rubber band pulls a wooden slider back along its guide once the slider is released.
- [`scarf_chair_slip`](scarf_chair_slip/README.md): A fringed cotton scarf slides off a chair backrest and lands in a heap on the seat.
- [`silicone_bag_can`](silicone_bag_can/README.md): A metal can drops into a silicone tote hanging from counter hooks; the bag stretches and sways.
- [`silicone_block_chain`](silicone_block_chain/README.md): A steel ball rolls into a press rig whose platen compresses a foam block and tips up a hinged flag.
- [`slingshot_domino`](slingshot_domino/README.md): A tabletop slingshot launches a ball with elastic bands into a wooden domino.
- [`spring_block_step`](spring_block_step/README.md): A released spring pushes a wooden block off a raised board onto the tabletop.
- [`spring_car_collision`](spring_car_collision/README.md): A compressed coil spring launches a toy car into a free wooden block.
- [`spring_scale_weight_drop`](spring_scale_weight_drop/README.md): A 100 g weight drops onto the pan of a spring balance and loads its steel spring.
- [`steel_ball_tensioned_membrane`](steel_ball_tensioned_membrane/README.md): A steel ball falls onto a rubber membrane tensioned in a circular laboratory fixture.
- [`tennis_net_hit`](tennis_net_hit/README.md): A tennis ball hits a tensioned tennis net and is thrown back while the net sways and settles.
- [`thomas_dual_spring_train`](thomas_dual_spring_train/README.md): An unpowered blue toy train runs back and forth between guided compression springs at both ends of a wooden track.
- [`toy_car_silicone_bridge`](toy_car_silicone_bridge/README.md): A pushed toy car rolls across a silicone bridge clamped at both ends; the bridge sags and springs back (MuJoCo).
- [`wood_block_rubber_stop`](wood_block_rubber_stop/README.md): A sliding wooden block squashes a kitchen sponge against a table leg and bounces back.
- [`yoga_mat_rolled_edge`](yoga_mat_rolled_edge/README.md): A medicine ball rolls into the curled edge of a yoga mat.
