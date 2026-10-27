# Vertigo v3: the six cars rebuilt toward the 2026-10-26 design targets
# (design/vehicles/target-quality-2026-10-26). Runs inside Blender with the fleet .blend open:
#
#   blender -b assets/vehicles/vertigo-fleet.blend -P blender/run_v3.py -- <car-id> <steps> <out-dir>
#
# Each car's side silhouette (roof/hood/deck line, underside, wheel centres, window and door
# openings, intakes) was read off the side view of its target sheet in sheet pixels; spec() turns
# those into the loft profiles of vertigo_fleet.py at the car's registry length. On top of the
# fleet builder this adds: real glazing zones (windscreen, side and rear glass in dark tint, with
# opaque painted or black roof and pillars instead of a bubble canopy), intakes and grilles cut
# into the body, deck louvres, wheel-arch cladding, door handles, tail pipes with hollow bores,
# per-car wheel designs, and a studio sheet render matching the targets' three views.
import bpy, bmesh, math, os
from mathutils import Vector, Matrix

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if '__file__' in dir() else r'C:\Users\user\Desktop\AIA\Tesla'
F = {}
exec(open(os.path.join(REPO, 'blender', 'vertigo_fleet.py'), encoding='utf-8').read(), F)
material, pchip, lerp = F['material'], F['pchip'], F['lerp']

REGISTRY = {  # length, wheel radius and tail pipes from src/vehicles.js
    'vertigo-gt': dict(length=4.736, R=0.36, pipes=dict(r=0.05, tips=[(0.13, 0.38), (-0.13, 0.38)])),
    'vertigo-arc': dict(length=4.62, R=0.355, pipes=dict(r=0.042, tips=[(0.48, 0.30), (-0.48, 0.30)])),
    'vertigo-apex': dict(length=4.50, R=0.355, pipes=dict(r=0.038, tips=[(0.07, 0.40), (-0.07, 0.40), (0.20, 0.40), (-0.20, 0.40)])),
    'vertigo-grand': dict(length=4.96, R=0.37, pipes=dict(r=0.038, tips=[(0.40, 0.31), (0.53, 0.31), (-0.40, 0.31), (-0.53, 0.31)])),
    'vertigo-terra': dict(length=4.80, R=0.40, pipes=dict(r=0.055, tips=[(0.56, 0.56), (-0.56, 0.56)])),
    'vertigo-r': dict(length=4.68, R=0.355, pipes=dict(r=0.07, tips=[(0.0, 0.43)])),
}

# ---------------------------------------------------------------- measured targets (sheet pixels)
# front/rear: the car's ends in the side view; ground: tyre contact line; wf/wr: wheel centre x and
# tyre radius; top/bottom: silhouette points; belt: window sill line and its x span; ws: windscreen
# x span; side/quarter/rear: window spans; roof: paint, black or glass; doors: shut-line x pairs.
TARGETS = {
    'vertigo-gt': dict(
        base='vertigo-apex', name='Vertigo GT', paint='#ecebe6', paint_metal=0.12, paint_rough=0.2, sheet='01-gt-pearl-white', title='VERTIGO GT', colour='PEARL WHITE',
        front=45, rear=1440, ground=888, wf=(290, 101), wr=(1140, 104),
        top=[(52, 745), (70, 712), (110, 694), (160, 678), (210, 665), (270, 653), (330, 646), (390, 641), (440, 636), (490, 612), (540, 586), (590, 564),
             (640, 550), (700, 541), (770, 536), (850, 537), (905, 542), (940, 550), (1000, 563), (1100, 588), (1200, 616), (1280, 640), (1340, 656),
             (1385, 666), (1405, 676), (1430, 712)],
        bottom=[(52, 826), (90, 832), (200, 838), (420, 846), (700, 850), (1020, 848), (1250, 838), (1380, 828), (1430, 815)],
        belt=645, belt_span=(470, 880), gh_rear=1032, ws=(440, 640), side=[(478, 878)], quarter=[(888, 1032)], rear_glass=None,
        sail=[(880, 645), (920, 636), (960, 624), (1000, 611), (1034, 598), (1060, 592)],
        roof='paint', pillar='black', doors=[(470, 880)], mirror=(560, 625), seat=760, hood_dip=0.19, nose_dip=0.25, deck_dip=0.16, tail_dip=0.0, cabin_w=0.90, width=0.955, hood_ramp=0.16, shoulder_crease=0.6, slab=1.0, nose_cap=(0.004, 0.82, 0.75), tail_cap=(0.004, 0.84, 0.6),
        nose_w=[(0.0, 0.76), (0.03, 0.87), (0.08, 0.925), (0.16, 0.95), (0.35, 0.965)],
        intake=[(912, 778), (942, 778), (1008, 692), (984, 688)], louvres=(1000, 1175, 0.25), hood_vents=False,
        quarter_louvres=[(896, 1022, 600), (896, 992, 612), (896, 955, 624)],
        grille=dict(hw=0.54, hwb=0.6, z0=0.235, z1=0.36, r=0.05), corner_vents=dict(y=0.70, x=0.08, z0=0.22, z1=0.43, w=0.055, lean=0.035, yaw=35),
        lamp=dict(y0=0.42, y1=0.88, z0=0.545, rise=0.075, width=0.1, drl=0.03, style='v3'), drl_w=0.016, leds=3, hood_slots=dict(x=1.12, y0=0.56, y1=0.68, w=0.035, sweep=0.12),
        tail_px=680, tail_style='gt', tail_y=0.76, tail_wrap=0.0, rear_band=(0.022, 0.075), rear_band_y=0.6, tail_centre=dict(y=0.52, dz=-0.048),
        diffuser_h=0.12, diffuser_y=0.62, diffuser_zc=0.2, rear_mouth=dict(hw=0.5, hwb=0.62, z0=0.2, z1=0.44, r=0.06, depth=0.16), fin_y=(-0.56, -0.42, -0.28, 0.28, 0.42, 0.56), rocker=dict(h=0.12, rise=0.035, run=0.5, at='rear'),
        wheel=dict(sets=[dict(count=5, r_in=0.098, r_out=0.264, w_in=0.042, w_out=0.135, twist=-0.22, round=2.6)], rim_r=0.292, dish=0.05, cap='silver', cap_r=0.05, lip='face',
                   caliper_f=(128, 232), caliper_r=(-52, 52), face='RimFace'), rim='silver',
        splitter=True, fins=5, fin_size=(0.3, 0.12), roof_rail=0.02, valley=True, ledge=0.07, arch_gap=0.022,
        hubs=dict(front=dict(wheel_FR=(366, 269), wheel_RR=(73, 196)), rear=dict(wheel_RL=(311, 266), wheel_FL=(57.5, 201))),
        right_rows=dict(front=(40, 300), rear=(115, 305)),
        glass_frame=dict(line=[(655, 556), (700, 560), (760, 557), (800, 557), (850, 561), (900, 570), (950, 585), (990, 599), (1034, 613)], w=0.05),
        pillars=[([(472, 646), (560, 600), (655, 556)], 0.05), ([(899, 638), (891, 568)], 0.014)],
        door_cut=[[(484, 818), (479, 760), (477, 700), (483, 668), (498, 650)], [(866, 818), (878, 760), (893, 700), (903, 668), (906, 652)]],
        sculpt=[
            dict(op='bump', at=(1.6, 0.0, 0.62), r=(0.9, 0.4, 0.5), d=0.025, dir=(0, 0, 1)),  # raised hood centre
            dict(op='bump', at=(-1.3, 0.92, 0.72), r=(0.6, 0.3, 0.28), d=0.05),  # rear haunches
            dict(op='line', pts=[(1.05, None, 0.42), (0.5, None, 0.44), (-0.2, None, 0.5), (-0.62, None, 0.6)], d=-0.035, w=0.035, soft=0.13, fade=0.25),  # door scallop
        ],
    ),
    'vertigo-arc': dict(
        base='vertigo-arc', name='Vertigo Arc', paint='#5c8aab', paint_metal=0.55, paint_rough=0.22, sheet='02-arc-sky-blue', title='VERTIGO ARC', colour='SKY BLUE',
        front=112, rear=1408, ground=917, wf=(380, 106), wr=(1170, 106),
        top=[(113, 792), (117, 770), (124, 760), (132, 755), (152, 743), (172, 732), (192, 722), (212, 709), (232, 699), (252, 692), (272, 685), (292, 673),
             (312, 664), (332, 659), (352, 654), (372, 650), (392, 647), (412, 645), (450, 643), (500, 643), (545, 646), (600, 652), (700, 655), (800, 655),
             (900, 655), (990, 652), (1030, 650), (1072, 648), (1112, 647), (1152, 646), (1192, 645), (1232, 647), (1272, 652), (1312, 664), (1352, 677),
             (1385, 688), (1400, 698), (1407, 716)],
        bottom=[(113, 820), (118, 848), (140, 858), (200, 865), (260, 872), (500, 875), (700, 875), (1000, 873), (1260, 862), (1330, 848), (1400, 836), (1407, 818)],
        belt=655, belt_span=(560, 1020), cockpit=(560, 1020), shield=570, shield_x=745, doors=[(575, 962)], mirror=(680, 652), seat=870,
        hood_dip=0.09, nose_dip=0.8, deck_dip=0.0, slab=0.6, flare=(0.03, 0.012), shoulder_crease=0.45, tail_cap=(0.004, 0.86, 0.45),
        cams={'front': ((0.83, -0.56), 2.3), 'rear': ((-0.86, 0.5), 2.2)},
        nose_w=[(0.0, 0.55), (0.06, 0.69), (0.15, 0.79), (0.3, 0.86), (0.5, 0.91), (0.72, 0.935)],
        tail_w=[(0.0, 0.52), (0.05, 0.67), (0.12, 0.79), (0.25, 0.89), (0.45, 0.955)],
        grille=dict(hw=0.46, hwb=0.52, z0=0.23, z1=0.35, r=0.045), corner_vents=dict(y=0.62, x=0.1, z0=0.24, z1=0.40, w=0.026, lean=0.0, yaw=40),
        lamp=dict(y0=0.48, y1=0.78, z0=0.56, rise=0.04, width=0.08, drl=0.03, style='oval', at=(200, 740), y=0.6, size=(0.13, 0.088), dir=(-1, -0.38, -0.12)),
        tail_px=712, tail_style='bar', tail_y=0.74, tail_wrap=0.2, tail_bar_w=0.03,
        diffuser_h=0.1, diffuser_y=0.76, diffuser_zc=0.35, fin_y=(), rocker=dict(h=0.10, rise=0.0, run=0.5),
        wheel=dict(sets=[dict(count=5, r_in=0.095, r_out=0.264, w_in=0.04, w_out=0.15, round=3.0),
                         dict(count=5, r_in=0.16, r_out=0.26, w_in=0.007, w_out=0.019, phase=0.5)], rim_r=0.288, cap='red', face='RimFace',
                   caliper_f=(128, 232), caliper_r=(-52, 52)), rim='polished', hump=(0.8, 1.0), hoop_h=1.35,
        splitter=False, fins=0,
        hubs=dict(front=dict(wheel_FR=(365, 273), wheel_RR=(65, 190)), rear=dict(wheel_RL=(255, 263), wheel_FL=(43, 174))),
        right_rows=dict(front=None, rear=None),  # the rear view's right edge runs into the exhaust and floor shadow
    ),
    'vertigo-apex': dict(
        base='vertigo-apex', name='Vertigo Apex', paint='#827d93', paint_metal=0.5, paint_rough=0.22, sheet='03-apex-lavender', title='VERTIGO APEX', colour='LAVENDER',
        front=72, rear=1474, ground=904, wf=(356, 104), wr=(1221, 104),
        top=[(72, 800), (74, 790), (78, 780), (90, 770), (100, 766), (120, 752), (140, 740), (160, 732), (180, 724), (200, 716), (220, 709), (240, 701),
             (260, 693), (280, 686), (300, 679), (320, 674), (340, 669), (360, 664), (380, 662), (400, 661), (437, 662), (460, 659), (480, 650), (500, 642),
             (520, 633), (540, 625), (560, 618), (580, 610), (600, 603), (620, 596), (640, 590), (660, 584), (680, 580), (700, 576), (720, 573), (740, 570),
             (760, 568), (800, 567), (840, 567), (880, 569), (920, 573), (960, 578), (1000, 585), (1040, 592), (1080, 600), (1120, 607), (1160, 616),
             (1200, 625), (1240, 633), (1280, 633), (1320, 635), (1360, 642), (1400, 651), (1440, 653), (1462, 656), (1472, 668), (1474, 690)],
        bottom=[(72, 830), (76, 850), (100, 858), (200, 862), (300, 872), (500, 878), (700, 880), (1000, 878), (1150, 874), (1350, 866), (1420, 860), (1460, 850), (1474, 830)],
        belt=681, belt_span=(445, 881), gh_rear=1000, ws=(437, 690), side=[(450, 880)], quarter=[(886, 1000)], rear_glass=None,
        sail=[(881, 681), (920, 668), (960, 655), (1000, 641), (1030, 636)],
        roof='black', pillar='black', doors=[(494, 915)], mirror=(545, 668), seat=790, hood_dip=0.1, nose_dip=0.7, deck_dip=0.1, hood_ramp=0.2,
        cabin_w=0.9, width=0.97, shoulder_crease=0.6, slab=0.9, nose_cap=(0.004, 0.82, 0.7), tail_cap=(0.004, 0.84, 0.6),
        cams={'front': ((0.78, -0.62), 2.0), 'rear': ((-0.85, 0.52), 1.9)},
        intake=[(937, 806), (985, 806), (1078, 700), (1030, 700)], louvres=(1010, 1200, 0.32), hood_vents=False,
        quarter_louvres=[(890, 990, 628), (890, 970, 642), (890, 940, 656)],
        grille=dict(hw=0.42, hwb=0.5, z0=0.19, z1=0.31, r=0.04), corner_vents=dict(y=0.64, x=0.12, z0=0.17, z1=0.4, w=0.05, lean=0.06, yaw=28),
        lamp=dict(y0=0.36, y1=0.82, z0=0.42, rise=0.05, width=0.07, drl=0.02, style='v3'), leds=2,
        hood_slots=dict(x=0.5, y0=0.24, y1=0.44, w=0.04, sweep=0.12),
        tail_px=683, tail_style='split', tail_y=0.8, rear_band=(-0.02, 0.035), rear_band_y=0.72,
        rear_mouth=dict(hw=0.7, hwb=0.56, z0=0.24, z1=0.5, r=0.06, depth=0.16), diffuser_h=0.22, diffuser_y=0.6, diffuser_zc=0.2,
        fin_y=(-0.4, -0.2, 0.0, 0.2, 0.4), rocker=dict(h=0.11, rise=0.03, run=0.5, at='rear'),
        wheel=dict(sets=[dict(count=10, r_in=0.105, r_out=0.266, w_in=0.024, w_out=0.074, round=3.5)], rim_r=0.29, dish=0.05, lip='face', cap='red',
                   caliper_f=(128, 232), caliper_r=(-52, 52), face='RimFace'), rim='silver',
        splitter=True, fins=5, valley=True, ledge=0.06,
        hubs=dict(front=dict(wheel_FR=(374, 292), wheel_RR=(72, 198)), rear=dict(wheel_RL=(308, 234), wheel_FL=(72, 156))),
        right_rows=dict(front=None, rear=(90, 310)),
        pillars=[([(882, 676), (873, 602)], 0.014)],
    ),
    'vertigo-grand': dict(
        base='vertigo-grand', name='Vertigo Grand', paint='#0d3b28', paint_metal=0.55, paint_rough=0.2, sheet='04-grand-forest-green', title='VERTIGO GRAND', colour='FOREST GREEN',
        front=95, rear=1402, ground=896, wf=(308, 96), wr=(1127, 96),
        top=[(96, 760), (100, 735), (115, 717), (140, 695), (180, 675), (220, 662), (280, 652), (330, 645), (400, 642), (461, 641), (520, 612), (580, 582),
             (654, 550), (740, 536), (840, 529), (947, 532), (1054, 546), (1126, 568), (1197, 600), (1269, 636), (1340, 661), (1383, 671), (1398, 690), (1402, 720)],
        bottom=[(96, 785), (98, 820), (110, 833), (200, 840), (300, 848), (500, 860), (800, 862), (1000, 858), (1200, 848), (1340, 828), (1395, 808), (1402, 760)],
        belt=650, belt_span=(470, 1000), gh_rear=1290, ws=(461, 654), side=[(500, 793), (806, 1058), (1068, 1140)], quarter=[], rear_glass=(1140, 1290),
        sail=[(1000, 650), (1060, 644), (1100, 638), (1140, 634), (1200, 640), (1260, 652), (1320, 667), (1380, 680)],
        roof='glass', pillar='black', doors=[(480, 786), (790, 1062)], handles=[727, 1006], handle_py=692, mirror=(569, 640), seat=700,
        hood_dip=0.04, nose_dip=0.6, deck_dip=0.0, rear_seats=True, cabin_w=0.96, shoulder_crease=0.55, slab=0.7,
        nose_cap=(0.004, 0.84, 0.6), tail_cap=(0.004, 0.86, 0.55), flare=(0.035, 0.02),
        cams={'front': ((0.8, -0.6), 1.9), 'rear': ((-0.84, 0.54), 1.9)},
        grille=dict(hw=0.5, hwb=0.58, z0=0.2, z1=0.35, r=0.04), corner_vents=dict(y=0.66, x=0.08, z0=0.3, z1=0.47, w=0.035, lean=0.0, yaw=30),
        lamp=dict(y0=0.36, y1=0.82, z0=0.69, rise=0.02, width=0.05, drl=0.018, style='v3', wrap=dict(x0=0.04, x1=0.32, z1=0.7)), leds=3, front_bar=True, drl_w=0.016,
        tail_px=689, tail_style='bar', tail_y=0.8, tail_wrap=0.25, tail_bar_w=0.026,
        diffuser_h=0.17, diffuser_y=0.7, diffuser_zc=0.27, fin_y=(-0.24, -0.12, 0.0, 0.12, 0.24),
        rocker=dict(h=0.08, rise=0.0, run=0.5),
        wheel=dict(sets=[dict(count=14, r_in=0.1, r_out=0.264, w_in=0.012, w_out=0.05, twist=0.08, round=3.0)], rim_r=0.29, dish=0.05, cap='red',
                   caliper_f=(128, 232), caliper_r=(-52, 52), face='RimFace'), rim='graphite',
        splitter=False, fins=0, ledge=0.06,
        hubs=dict(front=dict(wheel_FR=(395, 290), wheel_RR=(71.5, 209)), rear=dict(wheel_RL=(352, 276), wheel_FL=(56, 182))),
        right_rows=dict(front=None, rear=(120, 300)),
        pillars=[([(797, 650), (800, 555)], 0.035), ([(1063, 645), (1060, 565)], 0.02)],
    ),
    'vertigo-terra': dict(
        base='vertigo-terra', name='Vertigo Terra', paint='#7a0f1c', paint_metal=0.55, paint_rough=0.2, sheet='05-terra-crimson', title='VERTIGO TERRA', colour='CRIMSON',
        front=108, rear=1366, ground=924, wf=(315, 101), wr=(1100, 101),
        top=[(108, 760), (110, 700), (118, 680), (160, 660), (260, 648), (360, 635), (460, 620), (520, 588), (590, 552), (660, 520), (720, 514), (800, 512),
             (900, 512), (1000, 513), (1100, 516), (1160, 530), (1230, 552), (1270, 585), (1300, 610), (1330, 628), (1360, 645), (1366, 700)],
        bottom=[(108, 800), (110, 830), (150, 845), (250, 852), (450, 858), (700, 860), (950, 860), (1200, 855), (1330, 835), (1366, 820)],
        belt=631, belt_span=(470, 1000), gh_rear=1240, ws=(460, 660), side=[(535, 773), (789, 1016), (1034, 1145)], quarter=[], rear_glass=(1150, 1290),
        sail=[(1000, 631), (1060, 622), (1110, 610), (1150, 596), (1200, 590), (1260, 612), (1320, 630), (1360, 645)],
        roof='black', pillar='black', doors=[(465, 760), (765, 1040)], handles=[720, 988], handle_py=668, mirror=(540, 615), seat=650,
        hood_dip=0.05, nose_dip=0.6, deck_dip=0.0, rear_seats=True, cladding=True, rails=True, roof_spoiler=False,
        cabin_w=0.95, shoulder_crease=0.6, slab=0.8, nose_cap=(0.004, 0.86, 0.6), tail_cap=(0.004, 0.86, 0.55), flare=(0.03, 0.02),
        nose_w=[(0.0, 0.68), (0.05, 0.8), (0.12, 0.88), (0.25, 0.94), (0.45, 0.97)], tail_w=[(0.0, 0.72), (0.05, 0.83), (0.12, 0.9), (0.25, 0.95)],
        cams={'front': ((0.82, -0.57), 2.4), 'rear': ((-0.85, 0.52), 1.95)},
        grille=dict(hw=0.58, hwb=0.66, z0=0.3, z1=0.5, r=0.05), corner_vents=dict(y=0.7, x=0.08, z0=0.52, z1=0.72, w=0.09, lean=0.0, yaw=25),
        lamp=dict(y0=0.4, y1=0.86, z0=0.9, rise=0.02, width=0.04, drl=0.014, style='v3', wrap=dict(x0=0.04, x1=0.2, z1=0.91)), drl_w=0.014, front_bar=False,
        lower_lamp=dict(z=0.68, y0=0.6, y1=0.82), lower_leds=3, front_band=(0.4, 0.6),
        tail_px=690, tail_style='bar', tail_y=0.8, tail_wrap=0.2, tail_bar_w=0.032,
        rear_band=None, diffuser_h=0.24, diffuser_y=0.8, diffuser_zc=0.52, diffuser_mat='Cladding', fin_y=(), rocker=dict(h=0.22, rise=0.0, run=0.5),
        wheel=dict(sets=[dict(count=6, r_in=0.1, r_out=0.262, w_in=0.03, w_out=0.1, twist=0.12, round=3.0),
                         dict(count=6, r_in=0.15, r_out=0.255, w_in=0.006, w_out=0.016, phase=0.5, twist=0.12)], rim_r=0.288, dish=0.04, cap='red',
                   caliper_f=(128, 232), caliper_r=(-52, 52), face='RimBlack'), rim='dark',
        splitter=False, fins=0, ledge=0.06,
        hubs=dict(front=dict(wheel_FR=(438, 301), wheel_RR=(82, 247)), rear=dict(wheel_RL=(325, 298), wheel_FL=(62, 220))),
        right_rows=dict(front=(130, 205), rear=(135, 300)),
        pillars=[([(775, 630), (785, 528)], 0.045), ([(1035, 622), (1020, 532)], 0.03)],
        glass_frame=dict(line=[(650, 527), (750, 523), (850, 522), (950, 524), (1050, 530), (1100, 537), (1140, 548)], w=0.035),
    ),
    'vertigo-r': dict(
        base='vertigo-r', name='Vertigo R', paint='#a2a8b2', paint_metal=0.7, paint_rough=0.2, sheet='06-r-cool-silver', title='VERTIGO R', colour='COOL SILVER',
        front=52, rear=1378, ground=892, wf=(332, 104), wr=(1130, 104),
        top=[(52, 790), (56, 760), (80, 735), (110, 716), (160, 695), (240, 670), (320, 652), (400, 640), (470, 630), (520, 608), (580, 580), (640, 560),
             (700, 549), (780, 545), (860, 550), (960, 572), (1060, 598), (1150, 612), (1250, 630), (1320, 643), (1360, 655), (1374, 680), (1378, 705)],
        bottom=[(52, 820), (58, 835), (100, 842), (300, 848), (700, 855), (1000, 852), (1250, 846), (1350, 832), (1378, 810)],
        belt=642, belt_span=(500, 820), gh_rear=968, ws=(470, 650), side=[(510, 866)], quarter=[(876, 1005)], rear_glass=None,
        sail=[(820, 642), (880, 630), (930, 618), (968, 608), (1000, 600)],
        roof='black', pillar='black', doors=[(490, 830)], handles=[785], handle_py=703, mirror=(545, 640), seat=720,
        hood_dip=0.12, nose_dip=0.75, deck_dip=0.08, hood_ramp=0.18, cabin_w=0.9, width=0.98, shoulder_crease=0.6, slab=0.9,
        nose_cap=(0.004, 0.82, 0.7), tail_cap=(0.004, 0.84, 0.6), cams={'front': ((0.8, -0.6), 1.7), 'rear': ((-0.84, 0.54), 1.9)},
        intake=[(880, 795), (905, 795), (965, 712), (940, 706)], louvres=None, hood_vents=True, stripe=True,
        hood_slots=dict(x=0.55, y0=0.26, y1=0.48, w=0.045, sweep=0.12),
        wing=dict(x_px=1345, top_py=555, chord=0.4, span=1.62, posts=0.34),
        grille=dict(hw=0.5, hwb=0.6, z0=0.17, z1=0.3, r=0.04), corner_vents=dict(y=0.68, x=0.1, z0=0.17, z1=0.38, w=0.05, lean=0.04, yaw=30),
        lamp=dict(y0=0.38, y1=0.84, z0=0.46, rise=0.06, width=0.075, drl=0.022, style='v3'), leds=2,
        tail_px=676, tail_style='split', tail_y=0.8, rear_band=(-0.02, 0.035), rear_band_y=0.74,
        rear_mouth=dict(hw=0.66, hwb=0.56, z0=0.24, z1=0.46, r=0.05, depth=0.16), diffuser_h=0.24, diffuser_y=0.62, diffuser_zc=0.18,
        fin_y=(-0.5, -0.3, -0.1, 0.1, 0.3, 0.5), rocker=dict(h=0.12, rise=0.03, run=0.5, at='rear'),
        wheel=dict(sets=[dict(count=5, r_in=0.1, r_out=0.264, w_in=0.045, w_out=0.13, round=2.6)], rim_r=0.292, dish=0.06, lip='face', cap='red',
                   caliper_f=(128, 232), caliper_r=(-52, 52), face='RimGraphite'), rim='gunmetal',
        splitter=True, fins=6, valley=True, ledge=0.06,
        hubs=dict(front=dict(wheel_FR=(359.5, 265.5), wheel_RR=(76, 190.5)), rear=dict(wheel_RL=(282, 262), wheel_FL=(62, 183))),
        right_rows=dict(front=None, rear=(130, 320)),
        pillars=[([(872, 650), (869, 565)], 0.012)],
        glass_frame=dict(line=[(680, 575), (750, 567), (800, 566), (850, 568), (900, 578), (950, 595), (1005, 619)], w=0.04),
    ),
}


# ---------------------------------------------------------------- spec
def spec(cid, fit=None):
    """The loft spec for a car: measured silhouette in metres, plus the base car's widths."""
    T, reg = TARGETS[cid], REGISTRY[cid]
    B = F['SPECS'][T['base']]
    k = reg['length'] / (T['rear'] - T['front'])
    xm = (T['front'] + T['rear']) / 2
    X = lambda px: (xm - px) * k
    Z = lambda py: (T['ground'] - py) * k
    top = {round(X(px), 4): Z(py) for px, py in T['top']}
    zb = {round(X(px), 4): Z(py) for px, py in T['bottom']}
    ztop_f = pchip(top)
    xs = sorted(top)
    x_lo, x_hi = xs[0], xs[-1]
    # Base widths, stretched onto the new length
    bx = sorted(B['ztop'])
    scale = lambda xb: x_lo + (xb - bx[0]) / (bx[-1] - bx[0]) * (x_hi - x_lo)
    W = {round(scale(x), 4): v * T.get('width', 1.0) for x, v in B['W'].items()}
    if T.get('nose_w'):
        cut = max(d for d, _ in T['nose_w'])
        W = {x: v for x, v in W.items() if x < x_hi - cut - 0.05}
        W.update({round(x_hi - d, 4): v * T.get('width', 1.0) for d, v in T['nose_w']})
    if T.get('tail_w'):
        cut = max(d for d, _ in T['tail_w'])
        W = {x: v for x, v in W.items() if x > x_lo + cut + 0.05}
        W.update({round(x_lo + d, 4): v * T.get('width', 1.0) for d, v in T['tail_w']})
    wcb = {round(scale(x), 4): v * T.get('cabin_w', 1.0) for x, v in B['wcb'].items()}
    bzb, bzbel = pchip(B['zb']), pchip(B['zbel'])
    zb_f = pchip(zb)
    zbel = {round(scale(x), 4): zb_f(scale(x)) + (bzbel(x) - bzb(x)) for x in sorted(B['zbel'])}
    # Shoulder: the window sill along the greenhouse; elsewhere just under the silhouette (the fenders),
    # with the hood / deck centre dipped below the fender crowns on the mid-engine cars.
    b0, b1 = X(T['belt_span'][1]), X(T['belt_span'][0])
    belt_z = Z(T['belt'])
    zsh, ztop = {}, {}
    gh0 = X(T.get('gh_rear', T['belt_span'][1]))
    ws_base = X(T['ws'][0]) if T.get('ws') else b1
    sail = T.get('sail')
    if sail:
        sail_f = pchip({round(X(px), 4): Z(py) for px, py in sail})
        sx0, sx1 = X(sail[-1][0]), X(sail[0][0])
        xs = sorted(set(xs) | {round(X(px), 4) for px, _ in sail})
    for x in xs:
        z = ztop_f(x)
        if sail and sx0 <= x < b0 - 0.02:
            zsh[x] = min(sail_f(x), z - 0.03) - 0.012
            ztop[x] = z
        elif gh0 <= x <= ws_base + 0.02:  # greenhouse: the shoulder is the window sill
            zsh[x] = belt_z - 0.012
            ztop[x] = z
        elif x > ws_base:  # hood
            zsh[x] = z - 0.012
            nose = T.get('nose_dip', 0.0)
            ztop[x] = z - T.get('hood_dip', 0) * min(1.0, (x - ws_base) / T.get('hood_ramp', 0.35)) * (nose + (1 - nose) * min(1.0, (x_hi - x) / 0.5))
        else:  # deck / tail
            zsh[x] = z - 0.015
            tail = T.get('tail_dip', 0.0)
            ztop[x] = z - T.get('deck_dip', 0) * max(0.0, min(1.0, (gh0 - x) / 0.35)) * (tail + (1 - tail) * min(1.0, (x - x_lo) / 0.5))
    S = dict(B)
    S.update(
        flare=T.get('flare', B['flare']),
        name=T['name'], paint=T.get('paint', B['paint']), paint_metal=T.get('paint_metal', B.get('paint_metal', 0.3)), paint_rough=T.get('paint_rough', 0.18),
        length=reg['length'], R=reg['R'], wb=(X(T['wr'][0]), X(T['wf'][0])),
        zb=zb, ztop=ztop, zsh=zsh, zbel=zbel, W=W, wcb=wcb,
        glass=(gh0, ws_base) if T.get('ws') else None,
        shuts=[(X(a), X(b)) for a, b in T.get('doors', [])],
        mirror=(X(T['mirror'][0]), Z(T['mirror'][1])), seat_x=X(T['seat']), rear_seats=T.get('rear_seats', False),
        lamp=T['lamp'], lower_lamp=T.get('lower_lamp'), front_bar=T.get('front_bar', False), projectors=False,
        tail=dict(z=Z(T['tail_px']), y=B['tail']['y'], width=0.05), tail_style=T.get('tail_style', 'bar'),
        intake_z=zb_f(x_hi - 0.05) + 0.06, diffuser_z=zb_f(x_lo + 0.05) + 0.12, fins=T.get('fins', 0),
        splitter=T.get('splitter', False), scoop=None, pillars=(), vents=T.get('hood_vents', False), stripe=T.get('stripe', False),
        rails=T.get('rails', False), wing=None, cladding=T.get('cladding', False),
        wheel=T['wheel'],
    )
    if not S.get('lower_lamp'):
        S.pop('lower_lamp', None)  # the fleet details test for the key, not its value
    if T.get('cockpit'):
        a, b = T['cockpit']
        S['cabrio'] = dict(B['cabrio'], x0=X(b), x1=X(a), shield=Z(T['shield']) - belt_z, rake=(T['shield_x'] - a) * k)
        S['glass'] = None
    S['_T'], S['_X'], S['_Z'], S['_k'] = T, X, Z, k
    # Plan shape fitted to the target's 3/4 views (blender/fit_v3.py): width along the car, cabin
    # width, and fender/haunch heights
    fp = os.path.join(REPO, 'blender', 'v3_fit', f'{cid}.json')
    if fit is None and globals().get('USE_FIT', True) and os.path.exists(fp):
        import json
        fit = json.load(open(fp))
    if fit:
        n = fit['stations']
        sta = lambda vals: pchip({round(x_lo + (x_hi - x_lo) * i / (n - 1), 4): v for i, v in enumerate(vals)})
        mf = sta(fit['W_mult'])
        S['W'] = {x: v * mf(x) for x, v in S['W'].items()}
        S['wcb'] = {x: v * fit['wcb_mult'] for x, v in S['wcb'].items()}
        if fit.get('zsh_dz'):
            df = sta(fit['zsh_dz'])
            g0, g1 = S['glass'] or (S['cabrio']['x0'], S['cabrio']['x1'])
            # (no clamp to the centreline: on the dipped hoods and decks the fender crowns stand above it)
            S['zsh'] = {x: (z + df(x) if not (g0 - 0.05 <= x <= g1 + 0.05) else z) for x, z in S['zsh'].items()}
        apply_regions(S, fit.get('regions', {}))  # nose and tail volumes fitted to all three views (blender/fit_views.py)
        S['_fit'] = fit
    return S


def apply_regions(S, regions):
    """Plan width multipliers and shoulder (fender / haunch crown) offsets at stations measured in
    from the nose ('front') or the tail ('rear'), easing back to the spec shape at d_fix. Shoulder
    offsets skip the greenhouse, where the shoulder is the window sill."""
    x_lo, x_hi = min(S['ztop']), max(S['ztop'])
    g0, g1 = S['glass'] or (S['cabrio']['x0'], S['cabrio']['x1'])
    for end, r in regions.items():
        at = (lambda d: x_hi - d) if end == 'front' else (lambda d: x_lo + d)
        inside = (lambda x: x > x_hi - r['d_fix']) if end == 'front' else (lambda x: x < x_lo + r['d_fix'])
        d_all = list(r['d']) + [r['d_fix'], r['d_fix'] + 0.4]
        mf = pchip({round(at(d), 4): m for d, m in zip(d_all, list(r['W_mult']) + [1.0, 1.0])})
        df = pchip({round(at(d), 4): z for d, z in zip(d_all, list(r['zsh_dz']) + [0.0, 0.0])})
        S['W'] = {x: (v * mf(x) if inside(x) else v) for x, v in S['W'].items()}
        S['zsh'] = {x: (z + df(x) if inside(x) and not (g0 - 0.05 <= x <= g1 + 0.05) else z) for x, z in S['zsh'].items()}
    return S


# ---------------------------------------------------------------- materials
def bsdf(m):
    return next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


def v3_materials(S):
    m = dict(F['shared_materials']())
    # Car paint: a mostly diffuse coloured base with a little metal in it, under a mirror clearcoat,
    # so the colour stays deep and the studio's softboxes draw crisp white highlights on top
    lin = [((int(S['paint'][i:i + 2], 16) / 255) ** 2.2) for i in (1, 3, 5)]
    if max(lin) >= 0.6:  # whites: keep shading in the body instead of clipping
        lin = [c * 0.5 for c in lin]
    else:  # coloured paints: a deeper base, the clearcoat supplies the brightness
        g = sum(lin) / 3  # deeper and a touch more saturated
        lin = [max(0.0, g + (c - g) * 1.05) * 0.6 for c in lin]
    m['Paint'] = material(f'Paint {S["name"]}', tuple(lin), min(0.3, S['paint_metal']), 0.34, 1.0)
    bsdf(m['Paint']).inputs['Coat IOR'].default_value = 1.6
    # lamp housings: dark smoked glass over a black reflector, satin enough not to mirror the softboxes
    m['LampHousing'] = material('V3 Lamp Housing', (0.003, 0.0032, 0.004), 0.0, 0.4, 0.35)
    bsdf(m['LampHousing']).inputs['Specular IOR Level'].default_value = 0.05
    m['Glass'] = material('V3 Tinted Glass', (0.012, 0.015, 0.018), 0.0, 0.05, 0.0, alpha=0.8)
    bsdf(m['Glass']).inputs['Specular IOR Level'].default_value = 0.08  # keep the cockpit readable through the glass
    m['LampGlass'] = material('V3 Lamp Glass', (0.9, 0.92, 0.95), 0.0, 0.02, 1.0, alpha=0.12)
    m['GlassDark'] = material('V3 Privacy Glass', (0.003, 0.004, 0.005), 0.0, 0.06, 0.0, alpha=0.94)
    bsdf(m['GlassDark']).inputs['Specular IOR Level'].default_value = 0.15
    m['RoofBlack'] = material('V3 Gloss Black', (0.006, 0.006, 0.007), 0.0, 0.08, 1.0)
    m['Trim'] = material('V3 Satin Black', (0.008, 0.0085, 0.01), 0.1, 0.5)
    bsdf(m['Trim']).inputs['Specular IOR Level'].default_value = 0.25
    m['Grille'] = material('V3 Grille', (0.005, 0.005, 0.006), 0.2, 0.55)
    m['Pipe'] = material('V3 Pipe', (0.62, 0.6, 0.57), 1.0, 0.28)
    m['Soot'] = material('V3 Soot', (0.008, 0.007, 0.007), 0.0, 0.85)
    m['WheelWell'] = material('V3 WheelWell', (0.004, 0.004, 0.005), 0.0, 0.9)
    rims = {'silver': ((0.56, 0.55, 0.53), 0.75, 0.28), 'polished': ((0.74, 0.74, 0.76), 0.9, 0.2), 'graphite': ((0.09, 0.095, 0.1), 0.8, 0.32),
            'dark': ((0.03, 0.03, 0.033), 0.6, 0.3), 'gunmetal': ((0.16, 0.165, 0.17), 0.85, 0.28)}
    col, met, rough = rims[S['_T']['rim']]
    face = S['wheel'].get('face', 'RimFace')
    m[face] = material(f'V3 Rim {S["_T"]["rim"]}', col, met, rough, 0.5)
    m['Caliper'] = material('V3 Caliper', '#c4161c', 0.15, 0.32, 0.6)
    m['Interior'] = material('V3 Leather', (0.011, 0.011, 0.012), 0.0, 0.55)
    m['Disc'] = material('V3 Disc', (0.2, 0.2, 0.205), 0.7, 0.38)
    m['Hat'] = material('V3 DiscHat', (0.05, 0.05, 0.055), 0.6, 0.4)
    m['Tire'] = material('V3 Tire', (0.008, 0.008, 0.009), 0.0, 0.82)
    m['TireWall'] = material('V3 TireWall', (0.011, 0.011, 0.012), 0.0, 0.66)
    for t in ('Tire', 'TireWall'):
        bsdf(m[t]).inputs['Specular IOR Level'].default_value = 0.3
    return m


# ---------------------------------------------------------------- body
GREEN_SIDE, GREEN_UPPER, ROOF = {8, 13}, {9, 12}, {10, 11}


def half_profile_v3(x, P):
    """The fleet's 12-point half section, with the window line carried higher up the roof flank so
    the side glass keeps the target's height after subdivision."""
    w, b, bel, sh, top, wc = (P[k](x) for k in ('W', 'zb', 'zbel', 'zsh', 'ztop', 'wcb'))
    t = max(0.0, min(1.0, (top - sh) / 0.15))
    t = t * t * (3 - 2 * t)
    if SLAB.get('valley'):
        # hood and deck between standing fenders: a steep inner fender wall down to a valley, then
        # a broad, nearly flat panel across the middle
        h8, h9, h10 = (0.68 * w, top + 0.5 * (sh - top)), (0.57 * w, top + 0.07 * (sh - top)), (0.3 * w, top + 0.004)
    else:
        h8, h9, h10 = (wc, top + 0.35 * (sh - top)), (0.70 * wc, top + 0.05 * (sh - top)), (0.35 * wc, top)
    g = SLAB['g'](x)
    # Tumblehome: the side glass starts a ledge inboard of the shoulder however wide the roof is,
    # and leans in from there to the roof edge
    wg = min(wc, (0.83 + 0.055 * g) * w - SLAB.get('ledge', 0.0)) if SLAB.get('ledge') else wc
    p8 = (lerp(h8[0], wg, t), lerp(h8[1], sh + 0.012, t))
    p9 = (lerp(h9[0], max(0.965 * wg, 0.86 * wc + 0.01), t), lerp(h9[1], sh + 0.62 * (top - sh), t))
    p10 = (lerp(h10[0], 0.86 * wc, t), lerp(h10[1], top - SLAB.get('rail', 0.016), t))
    # Flank heights from the sill up to the shoulder. Near the nose and tail there isn't room for
    # the nominal stack (the belly line would cross the bumper corner and fold the face), so there
    # the points spread evenly over the height instead.
    nominal = (b + 0.05, b + 0.16, bel, bel + 0.13, sh - 0.075)
    room = sh - b
    k = max(0.0, min(1.0, (room - 0.3) / 0.2))
    z = [lerp(b + f * room, n, k) for f, n in zip((0.1, 0.32, 0.52, 0.72, 0.88), nominal)]
    for i in range(1, len(z)):
        z[i] = max(z[i], z[i - 1] + 0.004)
    return [(0.0, b), (0.78 * w, b), (0.90 * w, z[0]), (0.965 * w, z[1]), (w, z[2]), ((0.98 + 0.01 * g) * w, z[3]),
            ((0.92 + 0.035 * g) * w, z[4]), ((0.83 + 0.055 * g) * w, sh), p8, p9, p10, (0.0, top)]


SLAB = {'g': lambda x: 0.0}  # per car, along x: 0 keeps the fleet's tumblehome, 1 pushes flank and shoulder out
F['half_profile'] = half_profile_v3


def build_body_v3(cid, S, coll, mats):
    """The fleet loft with glazing zones: glass only where the target has windows."""
    body, cutter = F['build_body'](cid, S, coll, mats)
    T, X = S['_T'], S['_X']
    arch_cutter(cid, S, cutter, T.get('arch_gap', 0.045))
    N = len(F['ring'](0, {k: pchip(S[k]) for k in ('W', 'zb', 'zbel', 'zsh', 'ztop', 'wcb')}))
    me = body.data
    ca = me.attributes.get('crease_edge') or me.attributes.new('crease_edge', 'FLOAT', 'EDGE')
    nring = (len(me.vertices) - 2 * N) // N
    # End caps: the fleet closes each end with a domed cap; flatten it into a real face (bumper
    # face, tail panel) and crease its outline so the hood and deck end on a defined edge.
    for key, ring_i, inner in (('nose_cap', nring - 1, nring * N + N), ('tail_cap', 0, nring * N)):
        cap = T.get(key)
        if not cap: continue
        dx, sc, cr = cap
        ring = [me.vertices[ring_i * N + k].co.copy() for k in range(N)]
        cz = sum(v.z for v in ring) / N
        sgn = 1 if key == 'nose_cap' else -1
        for k, v in enumerate(ring):
            me.vertices[inner + k].co = (v.x + sgn * dx, v.y * sc, cz + (v.z - cz) * sc)
        for e in me.edges:
            a, b = e.vertices
            if a // N == ring_i and b // N == ring_i and a < nring * N and b < nring * N:
                ca.data[e.index].value = max(ca.data[e.index].value, cr)
    for e in me.edges:
        a, b = e.vertices
        if a >= nring * N or b >= nring * N: continue
        if a % N == b % N and a % N in (7, 15) and abs(a // N - b // N) == 1:
            ca.data[e.index].value = max(ca.data[e.index].value, T.get('shoulder_crease', 0.3))
    me = body.data
    me.materials.clear()
    for k in ('Paint', 'Glass', 'Trim', 'Cladding', 'GlassDark', 'RoofBlack', 'Grille'):
        me.materials.append(mats[k])
    slot = {k: i for i, k in enumerate(('Paint', 'Glass', 'Trim', 'Cladding', 'GlassDark', 'RoofBlack', 'Grille'))}
    span = lambda px: (min(X(px[0]), X(px[1])), max(X(px[0]), X(px[1])))
    inside = lambda x, r: r[0] <= x <= r[1]
    ws = span(T['ws']) if T.get('ws') else None
    sides = [span(s) for s in T.get('side', [])]
    quarters = [span(s) for s in T.get('quarter', [])]
    rear = span(T['rear_glass']) if T.get('rear_glass') else None
    gh = (X(T.get('gh_rear', T['belt_span'][1])), ws[1] if ws else X(T['belt_span'][0]))
    roof = {'paint': 'Paint', 'black': 'RoofBlack', 'glass': 'GlassDark'}[T.get('roof', 'paint')]
    pillar = 'Trim' if T.get('pillar') == 'black' else 'Paint'  # satin, so pillars never flare white
    # Ring band index of each face: the loft's faces come ring by ring, N per band.
    N = len(F['ring'](0, {k: pchip(S[k]) for k in ('W', 'zb', 'zbel', 'zsh', 'ztop', 'wcb')}))
    for f, p in enumerate(me.polygons):
        i, x = f % N, p.center.x
        if p.material_index != 0 and p.material_index != 1:
            continue  # trim and cladding stay
        name = 'Paint'
        if ws and i in GREEN_SIDE | GREEN_UPPER | ROOF and inside(x, ws):
            name = 'Glass'
        elif ws and i in GREEN_UPPER | ROOF and ws[1] < x <= ws[1] + T.get('ws_drop', 0.0):
            name = 'Glass'  # the screen runs on down into the hood valley between the fenders
        elif rear and i in GREEN_UPPER | ROOF and inside(x, rear):
            name = 'GlassDark'
        elif i in GREEN_SIDE | GREEN_UPPER and any(inside(x, s) for s in sides):
            name = 'Glass'
        elif i in GREEN_SIDE | GREEN_UPPER and any(inside(x, q) for q in quarters):
            name = 'GlassDark'
        elif i in ROOF and inside(x, gh):
            name = roof
        elif i in GREEN_SIDE | GREEN_UPPER and inside(x, gh):
            name = pillar
        p.material_index = slot[name]
    me.update()
    return body, cutter


# ---------------------------------------------------------------- hand sculpting
# The loft gives the silhouette; the surface inside it (fender crowns standing over a lower hood, a
# nose whose corners sweep back, a door scallop running into the side intake, crisp character lines)
# is shaped here on the subdivided shell. Each car's TARGETS['sculpt'] lists the moves, in metres in
# body space (x forward, y left, z up), mirrored to both sides:
#   bump  at, r=(rx, ry, rz), d, dir='n' | (dx, dy, dz), p=2  - a smooth ellipsoid push, along the
#         surface normal or a fixed direction (y mirrored), p > 2 for a flatter top
#   line  pts=[(x, y, z), ...], d, w, soft, side=(sx, sy, sz)  - a character line along a curve: the
#         surface lifts by d at the curve, falls off over w on the `side` half (the crisp edge) and over
#         soft on the other (the blend); d < 0 cuts a groove
def bake_subdivision(body, levels):
    """Apply the loft's Subdivision modifier into the mesh, so the sculpt moves work on the smooth
    shell (the arch and opening booleans after it stay live)."""
    sub = body.modifiers['Subdivision']
    sub.levels = sub.render_levels = levels
    rest = [m for m in body.modifiers if m != sub]
    for m in rest: m.show_viewport = False
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(body.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    for m in rest: m.show_viewport = True
    old = body.data
    body.data = me
    me.name = old.name
    bpy.data.meshes.remove(old)
    body.modifiers.remove(sub)
    for p in me.polygons: p.use_smooth = True


def sculpt(body, ops):
    import numpy as np
    me = body.data
    n = len(me.vertices)
    co = np.empty(n * 3); me.vertices.foreach_get('co', co); co = co.reshape(n, 3)
    for op in ops:
        me.vertices.foreach_set('co', co.ravel()); me.update()
        nor = np.empty(n * 3); me.vertex_normals.foreach_get('vector', nor); nor = nor.reshape(n, 3)
        sy = np.where(co[:, 1] < 0, -1.0, 1.0)
        q = co * np.stack([np.ones(n), sy, np.ones(n)], 1)  # mirrored onto the +y side
        qn = nor * np.stack([np.ones(n), sy, np.ones(n)], 1)
        if op.get('dir', 'n') == 'n':
            dirv = qn
        else:
            dirv = np.tile(np.array(op['dir'], float), (n, 1))
        if op['op'] == 'bump':
            c, r, p = np.array(op['at'], float), np.array(op['r'], float), op.get('p', 2.0)
            u = (np.abs((q - c) / r) ** p).sum(1) ** (1.0 / p)
            wgt = np.clip(1 - u * u, 0, 1) ** 2
        elif op['op'] == 'line':
            # a None coordinate snaps the point onto the surface: y = None takes the outermost flank
            # point at that (x, z), z = None the top of the surface at that (x, y)
            pts = []
            for x_, y_, z_ in op['pts']:
                if y_ is None:
                    near = (np.abs(q[:, 0] - x_) < 0.03) & (np.abs(q[:, 2] - z_) < 0.03)
                    y_ = float(q[near, 1].max())
                elif z_ is None:
                    near = (np.abs(q[:, 0] - x_) < 0.03) & (np.abs(q[:, 1] - y_) < 0.03)
                    z_ = float(q[near, 2].max())
                pts.append((x_, y_, z_))
            P = np.array(pts, float)
            best, bd, bt, seg_len = None, np.full(n, np.inf), None, []
            cum = 0.0
            for a, b in zip(P, P[1:]):
                ab = b - a
                L2 = float(ab @ ab)
                t = np.clip(((q - a) @ ab) / L2, 0, 1)
                c = a + t[:, None] * ab
                d = np.linalg.norm(q - c, axis=1)
                take = d < bd
                bd = np.where(take, d, bd)
                best = c if best is None else np.where(take[:, None], c, best)
                bt = np.where(take, cum + t * math.sqrt(L2), bt if bt is not None else 0.0)
                cum += math.sqrt(L2)
            side = np.array(op.get('side', (0, 0, 1)), float)
            s = np.sign(((q - best) @ side) + 1e-9)
            w, soft = op['w'], op.get('soft', op['w'] * 3)
            wgt = np.exp(-(bd / np.where(s > 0, w, soft)) ** 2)
            fade = op.get('fade', 0.08)  # ease in and out over the curve's ends
            wgt *= np.clip(np.minimum(bt, cum - bt) / fade, 0, 1) ** 2 * (3 - 2 * np.clip(np.minimum(bt, cum - bt) / fade, 0, 1))
            wgt *= bd < op.get('reach', 4 * soft)
        if 'z_min' in op: wgt *= co[:, 2] > op['z_min']
        disp = op['d'] * wgt[:, None] * dirv
        disp[:, 1] *= sy  # back to each vertex's own side
        print('STEP sculpt', op['op'], round(float(np.abs(disp).max()), 4), int((wgt > 0.1).sum()), 'of', n, flush=True)
        co = co + disp
    me.vertices.foreach_set('co', co.ravel())
    me.update()


def rounded_poly(pts, r, n=6):
    """A convex polygon (2D points, in order) with each corner rounded by a quadratic arc of size r."""
    out = []
    m = len(pts)
    for i in range(m):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % m])
        a = p1 + (p0 - p1).normalized() * min(r, (p0 - p1).length / 2)
        b = p1 + (p2 - p1).normalized() * min(r, (p2 - p1).length / 2)
        for k in range(n + 1):
            t = k / n
            out.append(tuple((1 - t) ** 2 * a + 2 * (1 - t) * t * p1 + t * t * b))
    return out


def grille_outline(g):
    """Front mouth in the y-z plane: a trapezoid (wider at the bottom) with rounded corners."""
    zc = (g['z0'] + g['z1']) / 2
    pts = [(g['hwb'], g['z0']), (g['hw'], g['z1']), (-g['hw'], g['z1']), (-g['hwb'], g['z0'])]
    return rounded_poly(pts, g.get('r', 0.05)), zc


def openings(cid, S, coll, mats, body):
    """Intakes, the front mouth and corner vents cut into the shell; the cut walls take the dark
    grille material and details_v3 closes each opening with a back plate and slats."""
    T, X, Z = S['_T'], S['_X'], S['_Z']
    bm = bmesh.new()
    Wf = pchip(S['W'])
    def prism(outline_xz, y_in, y_out):
        lo = [bm.verts.new((x, y_in, z)) for x, z in outline_xz]
        hi = [bm.verts.new((x, y_out, z)) for x, z in outline_xz]
        n = len(lo)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
        bm.faces.new(list(reversed(lo))); bm.faces.new(hi)
    def along_x(outline_yz, x0, x1, tf=lambda v: v):
        lo = [bm.verts.new(tf(Vector((x0, y, z)))) for y, z in outline_yz]
        hi = [bm.verts.new(tf(Vector((x1, y, z)))) for y, z in outline_yz]
        n = len(lo)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
        bm.faces.new(list(reversed(lo))); bm.faces.new(hi)
    if T.get('intake'):
        pts = [(X(px), Z(py)) for px, py in T['intake']]
        cx = sum(p[0] for p in pts) / len(pts)
        w = Wf(cx)
        for s in (1, -1):
            prism(pts, s * (w - 0.11), s * (w + 0.4))
    x_front = max(S['ztop'])
    g = T.get('grille')
    if g:
        g = dict(dict(hwb=g['hw'] * 1.1), **g)
        out, _ = grille_outline(g)
        along_x(out, x_front - g.get('depth', 0.16), x_front + 0.5)
    rm = T.get('rear_mouth')
    if rm:
        out, _ = grille_outline(dict(dict(r=0.05), **rm))
        x_rear = min(S['ztop'])
        along_x(out, x_rear - 0.5, x_rear + rm.get('depth', 0.15))
    cv = T.get('corner_vents')
    if cv:
        cv = cv if isinstance(cv, dict) else dict(y=0.74, x=0.0, z0=0.14, z1=0.36, w=0.045)
        for s in (1, -1):
            # a slanted slot through the bumper corner, cut along the corner's diagonal
            zc = (cv['z0'] + cv['z1']) / 2
            hz = (cv['z1'] - cv['z0']) / 2
            outline = rounded_poly([(cv['w'], -hz), (cv['w'] + cv.get('lean', 0.03), hz), (-cv['w'] + cv.get('lean', 0.03), hz), (-cv['w'], -hz)], 0.02)
            ang = s * math.radians(cv.get('yaw', 30))
            rot = Matrix.Rotation(ang, 3, 'Z')
            base = Vector((x_front - cv.get('x', 0.0), s * cv['y'], zc))
            along_x(outline, -0.14, 0.6, lambda v, rot=rot, base=base: base + rot @ v)
    L = S['lamp']
    if L.get('style') == 'oval':
        bpy.context.view_layer.update()
        ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
        S['_lamp_pose'] = {}
        for s in (1, -1):
            tgt = Vector((X(L['at'][0]), s * L['y'], Z(L['at'][1])))
            dd = L.get('dir', (-1, -0.35, -0.4))
            d = Vector((dd[0], dd[1] * s, dd[2])).normalized()
            ok, loc, nor, _ = ev.ray_cast(tgt - d * 3, d)
            if not ok: continue
            n = nor.normalized()
            t1 = n.cross(Vector((0, 0, 1))).normalized()
            t2 = n.cross(t1).normalized()
            S['_lamp_pose'][s] = (loc.copy(), n, t1, t2)
            a_, b_ = L['size']
            ring = [loc + t1 * a_ * math.cos(q * math.tau / 40) + t2 * b_ * math.sin(q * math.tau / 40) for q in range(40)]
            lo = [bm.verts.new(v - n * 0.07) for v in ring]
            hi = [bm.verts.new(v + n * 0.4) for v in ring]
            for i in range(40):
                j = (i + 1) % 40
                bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
            bm.faces.new(list(reversed(lo))); bm.faces.new(hi)
    if not bm.faces:
        bm.free()
        return None
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(f'{cid}_OpeningCutter'); bm.to_mesh(me); bm.free()
    me.materials.append(mats['Grille'])
    ob = bpy.data.objects.new(f'{cid}_OpeningCutter', me)
    coll.objects.link(ob)
    ob.hide_render = True
    ob.display_type = 'WIRE'
    mod = body.modifiers.new('Openings', 'BOOLEAN')
    mod.operation = 'DIFFERENCE'; mod.object = ob; mod.solver = 'EXACT'; mod.material_mode = 'TRANSFER'
    mod.use_self = True; mod.use_hole_tolerant = True
    return ob


def arch_cutter(cid, S, cutter, gap):
    """Rebuild the fleet's wheel-arch cutter with a tighter gap round the tyre."""
    R = S['R']
    xr, xf = S['wb']
    cbm = bmesh.new()
    # Outboard of the fender crown the arch takes its full gap; inboard (under the hood or deck valley,
    # which dips below the arch top) only a tight clearance round the tyre.
    y_crown = 0.84
    for ax in (xr, xf):
        for side in (1, -1):
            # a valley hood runs low between the tyres; its fenders stand over them, so no inner cut
            y_in = y_crown if S['_T'].get('valley') else 0.6
            for r, y0, y1 in ((R + gap, y_crown, 1.6), (R + 0.016, y_in, y_crown + 0.02)):
                bmesh.ops.create_cone(cbm, cap_ends=True, segments=72, radius1=r, radius2=r, depth=y1 - y0,
                                      matrix=Matrix.Translation((ax, side * (y0 + y1) / 2, R + 0.01)) @ Matrix.Rotation(math.pi / 2, 4, 'X'))
    bmesh.ops.recalc_face_normals(cbm, faces=cbm.faces)
    cbm.to_mesh(cutter.data); cbm.free()


# ---------------------------------------------------------------- extra details
def tools(cid, coll, mats, body):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(deps)
    def hit(o, d):
        ok, loc, nor, _ = ev.ray_cast(Vector(o), Vector(d).normalized())
        return (loc, nor) if ok else None
    def new_obj(name, bm, ms, smooth=True):
        me = bpy.data.meshes.new(f'{cid}_{name}'); bm.to_mesh(me); bm.free()
        for m in (ms if isinstance(ms, (list, tuple)) else [ms]): me.materials.append(mats[m])
        for p in me.polygons: p.use_smooth = smooth
        ob = bpy.data.objects.new(f'{cid}_{name}', me); coll.objects.link(ob); return ob
    def strip(name, pts, nors, width, mat, lift=0.006, solid=0.0):
        bm = bmesh.new(); rows = []
        for i, (p, n) in enumerate(zip(pts, nors)):
            t = (pts[min(len(pts) - 1, i + 1)] - pts[max(0, i - 1)]).normalized()
            side = n.cross(t).normalized()
            base = p + n * lift
            rows.append((bm.verts.new(base + side * width / 2), bm.verts.new(base - side * width / 2)))
        for (a0, a1), (b0, b1) in zip(rows, rows[1:]):
            bm.faces.new((a0, b0, b1, a1))
        ob = new_obj(name, bm, mat)
        if solid:
            s = ob.modifiers.new('Thickness', 'SOLIDIFY'); s.thickness = solid
        return ob
    return hit, new_obj, strip


def smooth_seq(seq, k):
    out = []
    for i in range(len(seq)):
        lo, hi = max(0, i - k), min(len(seq), i + k + 1)
        acc = Vector((0, 0, 0))
        for v in seq[lo:hi]: acc += v
        out.append(acc / (hi - lo))
    return out


def ribbon_v3(new_obj, name, samples, width, mat, lift=0.006, taper=None, solid=0.0, k=2):
    """A strip laid on the body along ray-cast samples [(point, normal)], smoothed like the fleet's."""
    samples = [h for h in samples if h]
    if len(samples) < 3: return None
    pts = smooth_seq([p for p, _ in samples], k)
    nors = [n.normalized() for n in smooth_seq([n for _, n in samples], 2 * k)]
    bm = bmesh.new(); rows = []
    for i, (p, n) in enumerate(zip(pts, nors)):
        t = (pts[min(len(pts) - 1, i + 1)] - pts[max(0, i - 1)]).normalized()
        side = n.cross(t).normalized()
        w = width * (taper(i / max(1, len(pts) - 1)) if taper else 1.0)
        base = p + n * lift
        rows.append((bm.verts.new(base + side * w / 2), bm.verts.new(base - side * w / 2)))
    for (a0, a1), (b0, b1) in zip(rows, rows[1:]):
        bm.faces.new((a0, b0, b1, a1))
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    if bm.faces and bm.faces[0].normal.dot(nors[0]) < 0:  # face out of the body, so painted strips shade like the body
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    ob = new_obj(name, bm, mat)
    if solid:
        m = ob.modifiers.new('Thickness', 'SOLIDIFY'); m.thickness = solid
    return ob


def band_v3(new_obj, name, cast, nu, nv, mat, lift=0.005):
    """A panel painted onto the body: cast(u, v) ray-casts the point at u along the panel and v across
    it (both 0..1), sampled on an nu x nv grid so the panel follows the body's curvature instead of
    cutting under it. Columns with a miss are dropped."""
    cols = []
    for i in range(nu):
        col = [cast(i / (nu - 1), j / (nv - 1)) for j in range(nv)]
        good = [c for c in col if c]
        if len(good) < 2: continue
        # where the panel runs off the body (under a rising bumper) it stops at the last hit
        last = good[0]
        fixed = []
        for c in col:
            last = c or last
            fixed.append(last)
        cols.append(fixed)
    if len(cols) < 2: return None
    bm = bmesh.new()
    grid = [[bm.verts.new(p + n * lift) for p, n in col] for col in cols]
    for c0, c1 in zip(grid, grid[1:]):
        for j in range(nv - 1):
            bm.faces.new((c0[j], c1[j], c1[j + 1], c0[j + 1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_obj(name, bm, mat)


def box_obj(new_obj, name, centre, size, mat, rot=None, bevel=0.0):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]; v.co.y *= size[1]; v.co.z *= size[2]
    if rot is not None:
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=rot)
    bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(centre))
    ob = new_obj(name, bm, mat, smooth=False)
    if bevel:
        b = ob.modifiers.new('Bevel', 'BEVEL'); b.width = bevel; b.segments = 2
    return ob


# fleet details that the v3 builders below replace
FLEET_REPLACED = ('Intake', 'IntakeCorner_', 'Projector_', 'TailHousing', 'TailBar', 'Diffuser', 'Fin_', 'Reverse_', 'Splitter')
FLEET_LAMPS = ('LampHousing_', 'LampDRL_', 'LampHook_')
FLEET_REPLACED += ('FrontLightBar',)


def front_v3(cid, S, coll, mats, body, hit, new_obj):
    T = S['_T']
    x_front = max(S['ztop'])
    front = x_front + 3
    rib = lambda *a, **k: ribbon_v3(new_obj, *a, **k)
    g = T.get('grille')
    if g:
        g = dict(dict(hwb=g['hw'] * 1.1), **g)
        h = hit((front, 0, g['z1'] + 0.035), (-1, 0, 0))
        fx = h[0].x if h else x_front
        # mesh: horizontal and vertical bars a little behind the face, in front of the pocket's back wall
        n = max(3, int((g['z1'] - g['z0']) / 0.026))
        for j in range(1, n):
            t = j / n
            z = g['z0'] + (g['z1'] - g['z0']) * t
            hw = g['hwb'] + (g['hw'] - g['hwb']) * t - 0.012
            box_obj(new_obj, f'GrilleBar_{j}', (fx - 0.05, 0, z), (0.03, 2 * hw, 0.0055), 'Trim')
        for j in range(-12, 13):
            y = j * g['hw'] / 12.5
            box_obj(new_obj, f'GrilleRib_{j}', (fx - 0.06, y, (g['z0'] + g['z1']) / 2), (0.03, 0.005, g['z1'] - g['z0'] - 0.01), 'Trim')
    # Headlamps: a dark housing with a light line along its top edge and round LED emitters. The
    # path runs across the front face and, with 'wrap', on back along the fender side.
    L = S['lamp']
    leds = T.get('leds', 0)
    wrap = L.get('wrap')
    def lamp_path(s, dz=0.0, n=40):
        pts = [hit((front, s * (L['y0'] + (L['y1'] - L['y0']) * u), L['z0'] + L['rise'] * u ** 1.3 + dz), (-1, 0, 0)) for u in [i / (n - 1) for i in range(n)]]
        if wrap:
            z1 = L['z0'] + L['rise']
            pts += [hit((x_front - wrap['x0'] - (wrap['x1'] - wrap['x0']) * u, s * 3, z1 + (wrap['z1'] - z1) * u + dz), (0, -s, 0)) for u in [i / 23 for i in range(1, 24)]]
        return [h for h in pts if h]
    for s in (1, -1):
        TT = 'L' if s > 0 else 'R'
        if L.get('style') == 'v3':
            path = lamp_path(s)
            rib(f'LampHousing_{TT}', path, L['width'], 'LampHousing', lift=0.008, k=3, taper=lambda u: 0.3 + 0.7 * math.sin(math.pi * u) ** 0.5)
            rib(f'LampDRL_{TT}', lamp_path(s, L['drl'] * 0.9), T.get('drl_w', 0.014), 'HeadLamp', lift=0.014, k=3, taper=lambda u: 0.4 + 0.6 * math.sin(math.pi * u) ** 0.3)
        for k in range(leds):
            u = 0.22 + 0.5 * k / max(1, leds - 1)
            if L.get('style') == 'v3':
                path = lamp_path(s, -0.008)
                h = path[int(len(path) * (0.18 + 0.4 * k / max(1, leds - 1)))] if path else None
            else:
                h = hit((front, s * (L['y0'] + (L['y1'] - L['y0']) * u), L['z0'] + L['rise'] * u ** 1.3 - 0.006), (-1, 0, 0))
            if not h: continue
            p, nrm = h
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=0.019, radius2=0.017, depth=0.014)
            lens = bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=0.012, radius2=0.012, depth=0.016)
            for f in {f for v in lens['verts'] for f in v.link_faces}: f.material_index = 1
            bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(nrm).to_matrix())
            bmesh.ops.translate(bm, verts=bm.verts, vec=p + nrm * 0.012)
            new_obj(f'LampLED_{TT}{k}', bm, ['LampHousing', 'HeadLamp'])
    # Oval lamps recessed into the fender fronts: polished bezel, glowing inner ring, projector, cover lens
    for s, (c, n, t1, t2) in S.get('_lamp_pose', {}).items():
        TT = 'L' if s > 0 else 'R'
        a_, b_ = L['size']
        def ellipse_ring(name, depth, sa, sb, tube, mat, steps=48, sides=8):
            bm = bmesh.new()
            g = []
            for q in range(steps):
                ang = q * math.tau / steps
                centre = c - n * depth + t1 * sa * math.cos(ang) + t2 * sb * math.sin(ang)
                radial = (t1 * sa * math.cos(ang) + t2 * sb * math.sin(ang)).normalized()
                g.append([bm.verts.new(centre + radial * tube * math.cos(k * math.tau / sides) + n * tube * math.sin(k * math.tau / sides)) for k in range(sides)])
            for q in range(steps):
                for k in range(sides):
                    bm.faces.new((g[q][k], g[(q + 1) % steps][k], g[(q + 1) % steps][(k + 1) % sides], g[q][(k + 1) % sides]))
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            return new_obj(name, bm, mat)
        ellipse_ring(f'LampBezel_{TT}', 0.008, a_ - 0.004, b_ - 0.004, 0.006, 'RimLip')
        ellipse_ring(f'LampRing_{TT}', 0.035, a_ * 0.78, b_ * 0.72, 0.0045, 'HeadLamp')
        # dark reflector bowl at the back of the pocket
        bm = bmesh.new()
        rim = [bm.verts.new(c - n * 0.066 + t1 * a_ * 0.98 * math.cos(q * math.tau / 40) + t2 * b_ * 0.98 * math.sin(q * math.tau / 40)) for q in range(40)]
        bm.faces.new(rim)
        new_obj(f'LampBowl_{TT}', bm, 'LampHousing')
        # projector: a short polished barrel with a glowing lens, set toward the inboard end
        bm = bmesh.new()
        res = bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=0.03, radius2=0.03, depth=0.04)
        lens = bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=0.021, radius2=0.021, depth=0.042)
        for f in {f for v in lens['verts'] for f in v.link_faces}: f.material_index = 1
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(n).to_matrix())
        bmesh.ops.translate(bm, verts=bm.verts, vec=c - n * 0.045 - t1 * a_ * 0.3 * s)
        new_obj(f'LampProjector_{TT}', bm, ['RimLip', 'HeadLamp'])
        # cover lens, gently domed
        bm = bmesh.new()
        rows = [[bm.verts.new(c - n * (0.004 - 0.006 * (1 - r * r)) + t1 * a_ * r * math.cos(q * math.tau / 40) + t2 * b_ * r * math.sin(q * math.tau / 40))
                 for q in range(40)] for r in (0.2, 0.6, 1.0)]
        for r0, r1 in zip(rows, rows[1:]):
            for q in range(40):
                bm.faces.new((r0[q], r0[(q + 1) % 40], r1[(q + 1) % 40], r1[q]))
        bm.faces.new(rows[0])
        new_obj(f'LampLens_{TT}', bm, 'LampGlass')
    if S.get('front_bar'):  # a full-width light line joining the lamps
        rib('FrontLightBar', [hit((front, -L['y0'] + 2 * L['y0'] * i / 63, L['z0'] + L['drl'] * 0.9), (-1, 0, 0)) for i in range(64)],
            T.get('drl_w', 0.014) * 0.8, 'HeadLamp', lift=0.014, k=3)
    ll = S.get('lower_lamp')
    for s in ((1, -1) if ll and T.get('lower_leds') else ()):
        for k in range(T['lower_leds']):
            h = hit((front, s * (ll['y0'] + (ll['y1'] - ll['y0']) * (k + 0.5) / T['lower_leds']), ll['z']), (-1, 0, 0))
            if not h: continue
            p, nrm = h
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=0.026, radius2=0.024, depth=0.02)
            lens = bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=0.017, radius2=0.017, depth=0.022)
            for f in {f for v in lens['verts'] for f in v.link_faces}: f.material_index = 1
            bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(nrm).to_matrix())
            bmesh.ops.translate(bm, verts=bm.verts, vec=p + nrm * 0.014)
            new_obj(f'LampLowLED_{s}_{k}', bm, ['RimLip', 'HeadLamp'])
    # Hood slots: one slanted vent each side of the bonnet
    hv = T.get('hood_slots')
    if hv:
        for s in (1, -1):
            pts = [hit((x_front - hv['x'] - hv.get('sweep', 0.06) * u, s * (hv['y0'] + (hv['y1'] - hv['y0']) * u), 4), (0, 0, -1)) for u in [i / 15 for i in range(16)]]
            rib(f'HoodSlot_{s}', pts, hv.get('w', 0.03), 'Soot', lift=0.003, taper=lambda u: 0.5 + 0.5 * math.sin(math.pi * u) ** 0.4)
    fb = T.get('front_band')
    if fb:
        band_v3(new_obj, 'FrontBand', lambda u, v: hit((front, 0.86 * (2 * u - 1), fb[1] - (fb[1] - fb[0]) * v), (-1, 0, 0)), 64, 6, 'Cladding', lift=0.006)
    # Splitter: a carbon blade under the nose that wraps round the corners
    if T.get('splitter'):
        zb_f = pchip(S['zb'])
        lip = [hit((front, -0.92 + 1.84 * u, zb_f(x_front - 0.12) + 0.045), (-1, 0, 0)) for u in [i / 47 for i in range(48)]]
        lip = [h for h in lip if h]
        bm = bmesh.new(); top, bot = [], []
        for p, nrm in lip:
            flat = Vector((nrm.x, nrm.y, 0)).normalized()
            top.append(bm.verts.new(p + flat * 0.045 + Vector((0, 0, -0.04))))
            bot.append(bm.verts.new(p - flat * 0.3 + Vector((0, 0, -0.04))))
        for i in range(len(top) - 1):
            bm.faces.new((top[i], top[i + 1], bot[i + 1], bot[i]))
        sp = new_obj('Splitter', bm, 'Trim')
        sol = sp.modifiers.new('Thickness', 'SOLIDIFY'); sol.thickness = 0.02


def rear_v3(cid, S, coll, mats, body, hit, new_obj):
    T = S['_T']
    x_rear = min(S['ztop'])
    rear = x_rear - 3
    rib = lambda *a, **k: ribbon_v3(new_obj, *a, **k)
    tl = S['tail']
    z = tl['z']
    ty = T.get('tail_y', 0.78)
    wrap = T.get('tail_wrap', 0.0)
    arch_c = lambda y: 0.012 * (1 - min(1.0, (y / ty) ** 2))
    def across(dz, y0, n=96):
        return [hit((rear, -y0 + 2 * y0 * i / (n - 1), z + dz + arch_c(-y0 + 2 * y0 * i / (n - 1))), (1, 0, 0)) for i in range(n)]
    def side(s, dz, rise, n=24):
        # forward along the top of the rear fender, rising a little
        return [hit((x_rear + 0.05 + wrap * i / (n - 1), s * 3, z + dz + rise * i / (n - 1)), (0, -s, 0)) for i in range(n)]
    def path(dz, rise=0.03):
        if not wrap: return across(dz, ty)
        return list(reversed(side(-1, dz, rise))) + across(dz, ty) + side(1, dz, rise)
    rib('TailHousing', path(0.0), tl.get('width', 0.05), 'LampHousing', lift=0.008, k=3)
    if S.get('tail_style') == 'gt':
        cb = T.get('tail_centre', dict(y=0.5, dz=-0.045))
        for s in (1, -1):
            seg = [hit((rear, s * (cb['y'] - 0.06 + (ty - cb['y'] + 0.06) * i / 31), z + 0.004 + 0.012 * i / 31), (1, 0, 0)) for i in range(32)]
            if wrap: seg += side(s, 0.004 + 0.012, 0.03)
            rib(f'TailOuter_{s}', seg, T.get('tail_outer_w', 0.032), 'BrakeLamp', lift=0.014, k=3, taper=lambda u: 0.35 + 0.65 * math.sin(math.pi * u) ** 0.2)
        rib('TailBar', [hit((rear, -cb['y'] + 2 * cb['y'] * i / 63, z + cb['dz']), (1, 0, 0)) for i in range(64)],
            T.get('tail_bar_w', 0.016), 'BrakeLamp', lift=0.014, k=3)
    elif S.get('tail_style') == 'split':
        for s in (1, -1):
            rib(f'TailBar_{s}', [hit((rear, s * (0.10 + (ty - 0.12) * i / 47), z + 0.012 + 0.02 * i / 47), (1, 0, 0)) for i in range(48)],
                T.get('tail_bar_w', 0.022), 'BrakeLamp', lift=0.014, k=3)
    else:
        rib('TailBar', path(0.004), T.get('tail_bar_w', 0.022), 'BrakeLamp', lift=0.014, k=3, taper=lambda u: 0.55 + 0.45 * math.sin(math.pi * u) ** 0.15)
    # A gloss-black band under the lamps, with the reversing lamps in it
    bz = T.get('rear_band')
    if bz:
        by = T.get('rear_band_y', ty * 0.92)
        band_v3(new_obj, 'RearBand', lambda u, v: hit((rear, by * (2 * u - 1), z - bz[0] - (bz[1] - bz[0]) * v), (1, 0, 0)), 64, 4, 'RoofBlack', lift=0.006)
        for s in (1, -1):
            rib('Reverse_' + ('L' if s > 0 else 'R'), [hit((rear, s * (0.22 + 0.16 * i / 11), z - (bz[0] + bz[1]) / 2), (1, 0, 0)) for i in range(12)],
                0.016, 'ReverseLamp', lift=0.012)
    # Diffuser: a black lower panel with vertical fins running back under the bumper
    dz = T.get('diffuser_zc', S['diffuser_z'])
    dh = T.get('diffuser_h', 0.16)
    if not bz:  # reversing lamps along the top of the lower bumper
        zr = T.get('reverse_z', dz + dh / 2 + 0.035)
        for s in (1, -1):
            rib('Reverse_' + ('L' if s > 0 else 'R'), [hit((rear, s * (0.26 + 0.14 * i / 11), zr), (1, 0, 0)) for i in range(12)],
                0.016, 'ReverseLamp', lift=0.012)
    dy = T.get('diffuser_y', 0.66)
    rm = T.get('rear_mouth')
    if rm:
        # mesh bars across the recessed rear mouth, just inside its opening
        h = hit((rear, 0, rm['z1'] + 0.03), (1, 0, 0))
        fx = h[0].x if h else x_rear
        n = max(3, int((rm['z1'] - rm['z0']) / 0.02))
        for j in range(1, n):
            t = j / n
            zz = rm['z0'] + (rm['z1'] - rm['z0']) * t
            hw = rm['hwb'] + (rm['hw'] - rm['hwb']) * t - 0.012
            box_obj(new_obj, f'RearMeshBar_{j}', (fx + 0.09, 0, zz), (0.015, 2 * hw, 0.003), 'Trim')
        for j in range(-22, 23):
            box_obj(new_obj, f'RearMeshRib_{j}', (fx + 0.1, j * rm['hw'] / 22.5, (rm['z0'] + rm['z1']) / 2), (0.015, 0.003, rm['z1'] - rm['z0'] - 0.01), 'Trim')
    else:
        band_v3(new_obj, 'Diffuser', lambda u, v: hit((rear, dy * (2 * u - 1), dz + dh / 2 - dh * v), (1, 0, 0)), 64, 6, T.get('diffuser_mat', 'Trim'), lift=0.006)
    for k, y in enumerate(T.get('fin_y', ())):
        h = hit((rear, y, dz), (1, 0, 0))
        if not h: continue
        p, _ = h
        # a vertical blade standing off the panel, its lower edge sweeping back and down
        fl, fh = T.get('fin_size', (0.22, dh * 0.62))
        box_obj(new_obj, f'Fin_{k}', (p.x + fl * 0.32, y, dz - dh * 0.18 - (fh - dh * 0.62) / 2), (fl, 0.012, fh), 'Trim',
                rot=Matrix.Rotation(math.radians(-10), 3, 'Y'))


def panels_v3(cid, S, coll, mats, body, hit, new_obj):
    """Painted-on black panels: the rocker (rising behind the front wheel), louvred engine-cover glass
    and quarter-window slats."""
    T, X, Z = S['_T'], S['_X'], S['_Z']
    rib = lambda *a, **k: ribbon_v3(new_obj, *a, **k)
    xr, xf = S['wb']
    R = S['R']
    zb_f = pchip(S['zb'])
    rk = T.get('rocker', dict(h=0.12, rise=0.1, run=0.6))
    for s in (1, -1):
        x0, x1 = xr + R + 0.06, xf - R - 0.04
        def cast(u, v, s=s, x0=x0, x1=x1):
            x = x0 + (x1 - x0) * u
            near = max(0.0, 1 - ((x - x0) if rk.get('at') == 'rear' else (x1 - x)) / rk['run'])
            top = zb_f(x) + rk['h'] + rk['rise'] * near ** 1.6
            return hit((x, s * 3, top - (top - zb_f(x) - 0.01) * v), (0, -s, 0))
        band_v3(new_obj, f'Rocker_{s}', cast, 64, 7, 'Trim', lift=0.006)
    lv = T.get('louvres')
    if lv:
        a, b = X(lv[1]), X(lv[0])
        hw = lv[2]
        band_v3(new_obj, 'LouvrePanel', lambda u, v: hit((a + (b - a) * u, hw * (1 - 2 * v), 4), (0, 0, -1)), 24, 12, 'GlassDark', lift=0.004)
        for j in range(10):
            xx = a + (b - a) * (j + 0.5) / 10
            rib(f'Louvre_{j}', [hit((xx, -hw + 0.02 + (2 * hw - 0.04) * u / 12, 4), (0, 0, -1)) for u in range(13)],
                (b - a) / 10 * 0.42, 'RoofBlack', lift=0.012, k=1)
    for j, (p0, p1, py) in enumerate(T.get('quarter_louvres', ())):
        a, b = X(p1), X(p0)
        for s in (1, -1):
            rib(f'QuarterSlat_{s}_{j}', [hit((a + (b - a) * u / 15, s * 3, Z(py)), (0, -s, 0)) for u in range(16)],
                0.01, 'RoofBlack', lift=0.006, k=1)
    # Side glass outline traced off the target's side view (sheet pixels): a body-colour frame along
    # the glass top (its lower edge on the traced line) and gloss-black pillars across the glazing
    def traced(line, dz=0.0, n=8):
        pts = [(X(a) + (X(b) - X(a)) * u / n, Z(c) + (Z(d) - Z(c)) * u / n + dz) for (a, c), (b, d) in zip(line, line[1:]) for u in range(n)]
        return pts + [(X(line[-1][0]), Z(line[-1][1]) + dz)]
    gf = T.get('glass_frame')
    if gf:
        for s in (1, -1):
            rib(f'GlassFrame_{s}', [hit((x, s * 3, z), (0, -s, 0)) for x, z in traced(gf['line'], gf['w'] / 2)], gf['w'], 'Paint', lift=0.004, k=2,
                taper=lambda u: min(1.0, u / 0.04, (1 - u) / 0.12))
    for j, (line, w) in enumerate(T.get('pillars', ())):
        for s in (1, -1):
            rib(f'Pillar_{s}_{j}', [hit((x, s * 3, z), (0, -s, 0)) for x, z in traced(line, n=12)], w, 'Trim', lift=0.005, k=1)
    # Door cut lines traced off the target's side view (sheet pixels), replacing the fleet's straight shuts
    for j, line in enumerate(T.get('door_cut', ())):
        pts = [(X(a) + (X(b) - X(a)) * u / 6, Z(c) + (Z(d) - Z(c)) * u / 6) for (a, c), (b, d) in zip(line, line[1:]) for u in range(6)]
        pts.append((X(line[-1][0]), Z(line[-1][1])))
        for s in (1, -1):
            rib(f'DoorCut_{s}_{j}', [hit((x, s * 3, z), (0, -s, 0)) for x, z in pts], 0.0045, 'Soot', lift=0.002, k=1)


def details_v3(cid, S, coll, mats, body):
    T, X, Z = S['_T'], S['_X'], S['_Z']
    hit, new_obj, strip = tools(cid, coll, mats, body)
    for o in list(coll.objects):
        short = o.name[len(cid) + 1:] if o.name.startswith(cid + '_') else ''
        if short and (any(short.startswith(p) for p in FLEET_REPLACED) or (S['lamp'].get('style') in ('v3', 'oval') and any(short.startswith(p) for p in FLEET_LAMPS))):
            bpy.data.objects.remove(o, do_unlink=True)
        elif short.startswith('Shut') and T.get('door_cut'):
            bpy.data.objects.remove(o, do_unlink=True)
    front_v3(cid, S, coll, mats, body, hit, new_obj)
    rear_v3(cid, S, coll, mats, body, hit, new_obj)
    panels_v3(cid, S, coll, mats, body, hit, new_obj)
    # Closed cars: a dark cabin tub, so the glass shows a cockpit floor and sides
    if S.get('glass'):
        g0, g1 = S['glass']
        zb_f, zsh_f, top_f, wcb_f = pchip(S['zb']), pchip(S['zsh']), pchip(S['ztop']), pchip(S['wcb'])
        xs_ = [g0 + (g1 - g0) * i / 20 for i in range(21)]
        hy = min(wcb_f(x) for x in xs_[2:-2]) - 0.05
        tub = F['rounded_rect']((g0 + g1) / 2, (g1 - g0) / 2 - 0.03, hy, 0.12)
        floor = zb_f((g0 + g1) / 2) + 0.07
        belt = min(zsh_f(x) for x in xs_[3:-3])
        ob = bpy.data.objects.new(f'{cid}_CabinTub', F['prism_mesh'](f'{cid}_CabinTub', tub, floor, belt - 0.015, mats['Interior'], cap_top=False, inward=True))
        coll.objects.link(ob)
        # (no separate headliner: the shell's inside renders dark, see backface_dark)
    x_rear = min(S['ztop'])
    # Tail pipes: a polished tube with a rolled lip and a soot-dark bore, mouths where the game puts the flames.
    pipes = REGISTRY[cid]['pipes']
    for i, (y, h) in enumerate(pipes['tips']):
        r = pipes['r']
        found = hit((x_rear - 3, y, h), (1, 0, 0))
        x = min(found[0].x if found else x_rear + 0.1, x_rear + 0.35) - 0.035
        rm = T.get('rear_mouth')
        if rm and rm['z0'] < h < rm['z1']:
            face = hit((x_rear - 3, y, rm['z1'] + 0.03), (1, 0, 0))
            x = (face[0].x if face else x_rear + 0.1) - 0.03  # tips stand proud of the mesh
        bm = bmesh.new()
        res = bmesh.ops.create_cone(bm, cap_ends=False, segments=32, radius1=r * 1.2, radius2=r * 1.15, depth=0.22)
        bmesh.ops.rotate(bm, verts=res['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'Y'))
        bmesh.ops.translate(bm, verts=res['verts'], vec=(x + 0.11, y, h))
        new_obj(f'PipeTube_{i}', bm, 'Pipe')
        bm = bmesh.new()
        MAJ, MIN, NU, NV = r * 1.1, r * 0.13, 32, 8
        g = [[bm.verts.new((x + MIN * math.sin(b), y + (MAJ + MIN * math.cos(b)) * math.cos(a), h + (MAJ + MIN * math.cos(b)) * math.sin(a)))
              for b in (j * math.tau / NV for j in range(NV))] for a in (q * math.tau / NU for q in range(NU))]
        for q in range(NU):
            for j in range(NV):
                bm.faces.new((g[q][j], g[(q + 1) % NU][j], g[(q + 1) % NU][(j + 1) % NV], g[q][(j + 1) % NV]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        new_obj(f'exhaust_{i}', bm, 'Pipe')
        bm = bmesh.new()
        res = bmesh.ops.create_circle(bm, cap_ends=True, segments=32, radius=r * 0.94)
        bmesh.ops.rotate(bm, verts=res['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(-math.pi / 2, 3, 'Y'))
        bmesh.ops.translate(bm, verts=res['verts'], vec=(x + 0.05, y, h))
        new_obj(f'PipeBore_{i}', bm, 'Soot')
        # inner wall of the double-walled tip
        bm = bmesh.new()
        res = bmesh.ops.create_cone(bm, cap_ends=False, segments=32, radius1=r, radius2=r, depth=0.06)
        bmesh.ops.rotate(bm, verts=res['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'Y'))
        bmesh.ops.translate(bm, verts=res['verts'], vec=(x + 0.03, y, h))
        new_obj(f'PipeInner_{i}', bm, 'Pipe')
    # Door handles (flush bars) and window frames along the sill
    for k, px in enumerate(T.get('handles', [])):
        for s in (1, -1):
            h = hit((X(px), s * 3, Z(T['handle_py'])), (0, -s, 0))
            if not h: continue
            p, n = h
            pts = [p + Vector((d, 0, 0)) for d in (-0.07, -0.035, 0, 0.035, 0.07)]
            strip(f'Handle_{k}_{s}', pts, [n] * 5, 0.022, 'Trim', lift=0.006)
    for a_px, b_px in (T.get('side', []) if T.get('ws') else []):
        a, b = X(b_px) + 0.03, X(a_px) - 0.06  # along the side windows only, clear of the A-pillar base
        for s in (1, -1):
            pts, nors = [], []
            for u in range(40):
                xx = a + (b - a) * u / 39
                h = hit((xx, s * 3, Z(T['belt']) - 0.004), (0, -s, 0))
                if h: pts.append(h[0]); nors.append(h[1])
            if len(pts) > 3:
                strip(f'Sill_{s}', pts, nors, 0.014, 'RoofBlack', lift=0.004)
    # Wheel-arch cladding (crossover): a matte black flare round each arch
    if T.get('cladding'):
        R = S['R']
        for ax in S['wb']:
            for s in (1, -1):
                pts, nors = [], []
                for u in range(32):
                    a = math.radians(-8 + 196 * u / 31)
                    o = (ax + (R + 0.11) * math.cos(a), s * 3, R + 0.02 + (R + 0.11) * math.sin(a))
                    h = hit(o, (0, -s, 0))
                    if h: pts.append(h[0]); nors.append(h[1])
                if len(pts) > 3:
                    strip(f'ArchFlare_{s}_{ax:+.1f}', pts, nors, 0.12, 'Cladding', lift=0.012, solid=0.02)
    # Roof spoiler (crossover)
    if T.get('roof_spoiler'):
        gx = X(T['gh_rear'])
        pts, nors = [], []
        for u in range(17):
            yy = -0.62 + 1.24 * u / 16
            h = hit((gx + 0.04, yy, 4), (0, 0, -1))
            if h: pts.append(h[0] + Vector((-0.12, 0, 0.02))); nors.append(Vector((0, 0, 1)))
        if len(pts) > 3:
            strip('RoofSpoiler', pts, nors, 0.28, 'RoofBlack', lift=0.0, solid=0.025)
    # Big rear wing on swan-neck posts (track car)
    wg = T.get('wing')
    if wg:
        wx, wz = X(wg['x_px']), Z(wg['top_py'])
        chord, span = wg['chord'], wg['span']
        prof = [(0, 0), (0.05, 0.03), (0.16, 0.04), (0.32, 0.028), (chord, 0.006), (0.3, -0.006), (0.14, -0.012), (0.05, -0.008)]
        bm = bmesh.new(); rows = []
        for y in (-span / 2, span / 2):
            rows.append([bm.verts.new((wx + chord / 2 - px, y, wz - 0.04 + pz - 0.05 * px)) for px, pz in prof])
        n = len(prof)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((rows[0][i], rows[0][j], rows[1][j], rows[1][i]))
        bm.faces.new(list(reversed(rows[0]))); bm.faces.new(rows[1])
        new_obj('Wing', bm, 'RoofBlack', smooth=False)
        for s in (1, -1):
            bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
            for v in bm.verts:
                v.co.x *= chord * 1.05; v.co.y *= 0.01; v.co.z *= 0.13
            bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((wx, s * span / 2, wz - 0.06)))
            new_obj(f'WingPlate_{s}', bm, 'RoofBlack', smooth=False)
            base = hit((wx - 0.05, s * wg['posts'], 4), (0, 0, -1))
            if not base: continue
            p = base[0]
            # swan neck: rises from the deck behind the wing and hooks over to its top surface
            path = [Vector((p.x - 0.02, s * wg['posts'], p.z)), Vector((p.x - 0.06, s * wg['posts'], (p.z + wz) / 2)),
                    Vector((wx - chord * 0.2, s * wg['posts'], wz + 0.05)), Vector((wx + chord * 0.15, s * wg['posts'], wz + 0.02))]
            bm = bmesh.new(); rows = []
            for q in range(len(path)):
                c = path[q]
                rows.append([bm.verts.new(c + Vector((dx, dy, 0))) for dx, dy in ((-0.05, -0.008), (0.05, -0.008), (0.05, 0.008), (-0.05, 0.008))])
            for a_, b_ in zip(rows, rows[1:]):
                for i in range(4):
                    j = (i + 1) % 4
                    bm.faces.new((a_[i], a_[j], b_[j], b_[i]))
            new_obj(f'SwanNeck_{s}', bm, 'RoofBlack', smooth=False)


# ---------------------------------------------------------------- wheels
def wheels_v3(cid, S, coll, mats):
    """The fleet wheel (tyre, barrel, polished lip, vented disc, hub, lugs, fixed caliper) with the
    spoke face cut by any number of window sets, so each car gets its target's design: a five-hole
    dish, V-spokes (big windows plus small ones in each V), ten or fourteen thin spokes, split spokes.
    Each set: count, r_in/r_out (radial span), w_in/w_out (half width at each end), twist (radians
    swept from hub to rim), pair (two windows per position), phase (in pitches), round (corner shape)."""
    MATS = ['Tire', S['wheel'].get('face', 'RimFace'), 'RimDark', 'Disc', 'RimLip', 'Lug', 'TireWall', 'Hat', 'Caliper']
    SLOT = {'Tire': 0, 'RimFace': 1, 'RimDark': 2, 'Disc': 3, 'RimLip': 4, 'Lug': 5, 'TireWall': 6, 'Hat': 7, 'Caliper': 8}
    Wp = S['wheel']
    sets = Wp.get('sets') or [dict(count=Wp['windows'], r_in=Wp['r_in'], r_out=Wp['r_out'], w_in=Wp['w_in'], w_out=Wp['w_out'],
                                   twist=Wp.get('twist', 0.0), pair=Wp.get('pair', 0.0))]
    dish = Wp.get('dish', 0.072)
    rr = Wp.get('rim_r', 0.276)            # outer radius of the rim lip (tyre bead), on the 0.362 m base wheel
    fr = rr - 0.018                        # spoke face outer edge
    tw = lambda r: rr + (r - 0.276) * (0.358 - rr) / (0.358 - 0.276)  # remap the fleet sidewall onto the new bead
    lip_mat = 'RimFace' if Wp.get('lip') == 'face' else 'RimLip'

    def window(ws, axis):
        R_IN, R_OUT, W_IN, W_OUT = ws['r_in'], ws['r_out'], ws['w_in'], ws['w_out']
        ROUND, POINTS, twist = ws.get('round', 4.0), 64, ws.get('twist', 0.0)
        mid, half = (R_IN + R_OUT) / 2, (R_OUT - R_IN) / 2
        pts = []
        for i in range(POINTS):
            t = i / POINTS * math.tau
            c, s_ = math.cos(t), math.sin(t)
            u = math.copysign(abs(c) ** (2 / ROUND), c)
            v = math.copysign(abs(s_) ** (2 / ROUND), s_)
            r = mid + u * half
            w = W_IN + (W_OUT - W_IN) * (u + 1) / 2
            phi = axis + (v * w) / r + twist * (r - R_IN) / (R_OUT - R_IN)
            pts.append(Vector((r * math.cos(phi), r * math.sin(phi))))
        return pts

    def tmp(name, bm, slot):
        for f in bm.faces: f.material_index = slot
        me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
        for m in MATS: me.materials.append(mats[m])
        o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
        return o

    # Spoke face: a dished disc (outer edge proud of the centre), cut by the window prisms
    bm = bmesh.new()
    prof = [(0.082 + (fr - 0.082) * (i / 24), 0.058 + dish * (i / 24) ** 1.4) for i in range(25)]
    loop = prof + [(r, y - 0.028) for (r, y) in reversed(prof)]
    vs = [bm.verts.new((0, y, r)) for (r, y) in loop]
    es = [bm.edges.new((a, b)) for a, b in zip(vs, vs[1:] + vs[:1])]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 1, 0), angle=math.tau, steps=144, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    disc = tmp('tmp_disc', bm, SLOT['RimFace'])
    bm = bmesh.new()
    for ws in sets:
        n, pair, phase = ws['count'], ws.get('pair', 0.0), ws.get('phase', 0.0)
        axes = [math.pi / 2 + (k + phase) * math.tau / n + d for k in range(n) for d in ((-pair / 2, pair / 2) if pair else (0.0,))]
        for axis in axes:
            outline = window(ws, axis)
            lo = [bm.verts.new((p.x, -0.2, p.y)) for p in outline]
            hi = [bm.verts.new((p.x, 0.3, p.y)) for p in outline]
            m = len(outline)
            for i in range(m):
                j = (i + 1) % m
                bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
            bm.faces.new(list(reversed(lo))); bm.faces.new(hi)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    cut = tmp('tmp_cut', bm, SLOT['RimDark'])
    mod = disc.modifiers.new('win', 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = cut; mod.solver = 'EXACT'; mod.material_mode = 'TRANSFER'
    mod.use_self = True
    mod.use_hole_tolerant = True
    bpy.context.view_layer.update()
    face = bpy.data.meshes.new_from_object(disc.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    print('STEP wheel face', len(face.polygons), 'faces', flush=True)
    for o in (disc, cut):
        m = o.data; bpy.data.objects.remove(o, do_unlink=True); bpy.data.meshes.remove(m)

    cap = Wp.get('cap', 'red')
    def wheel_bm():
        bm = bmesh.new()
        def lathe(profile, mat, steps=72):
            old = set(bm.faces)
            vs = [bm.verts.new((0, y, r)) for (r, y) in profile]
            es = [bm.edges.new((a, b)) for a, b in zip(vs, vs[1:])]
            bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 1, 0), angle=math.tau, steps=steps, use_merge=True)
            for f in bm.faces:
                if f not in old: f.material_index = SLOT[mat]
        # Tyre: rounded sidewalls with a rim-protector bead, and a tread with circumferential grooves
        lathe([(tw(0.276), -0.124), (tw(0.300), -0.134), (tw(0.328), -0.136), (tw(0.348), -0.124), (0.358, -0.100)], 'TireWall', 96)
        tread = [(0.358, -0.100), (0.3615, -0.088)]
        for gy in (-0.052, 0.0, 0.052):
            tread += [(0.3615, gy - 0.009), (0.3525, gy - 0.006), (0.3525, gy + 0.006), (0.3615, gy + 0.009)]
        tread += [(0.3615, 0.088), (0.358, 0.100)]
        lathe(tread, 'Tire', 128)
        lathe([(0.358, 0.100), (tw(0.348), 0.124), (tw(0.328), 0.136), (tw(0.306), 0.138), (tw(0.300), 0.143), (tw(0.293), 0.139),
               (tw(0.286), 0.133), (rr, 0.128)], 'TireWall', 96)
        # Rim: dark barrel, a stepped lip that meets the spoke face, then the face itself
        lathe([(rr, 0.128), (rr - 0.003, 0.075), (rr - 0.003, -0.115), (rr - 0.036, -0.12)], 'RimDark', 96)
        lathe([(rr, 0.128), (rr, 0.136), (rr - 0.004, 0.142), (rr - 0.01, 0.143), (rr - 0.016, 0.139), (fr, 0.13), (fr, 0.058 + dish - 0.004)], lip_mat, 96)
        # Ventilated disc: two plates with a dark gap, a dark hat in the middle
        dr = rr - 0.042  # disc outer radius
        lathe([(dr - 0.002, -0.044), (dr, -0.040), (dr, -0.032), (dr - 0.002, -0.030), (0.125, -0.030), (0.125, -0.044), (dr - 0.002, -0.044)], 'Disc', 64)
        lathe([(dr - 0.002, -0.026), (dr, -0.022), (dr, -0.014), (dr - 0.002, -0.010), (0.125, -0.010), (0.125, -0.026), (dr - 0.002, -0.026)], 'Disc', 64)
        lathe([(dr - 0.005, -0.030), (dr - 0.005, -0.026)], 'Hat', 64)
        lathe([(0.125, -0.044), (0.118, -0.02), (0.11, 0.0), (0.0, 0.0)], 'Hat', 48)
        # Hub and a round centre cap
        lathe([(0.0, 0.05), (0.083, 0.05), (0.086, 0.04), (0.086, 0.0)], 'RimDark', 36)
        centre = {'red': ('RimLip', 'Caliper'), 'silver': ('RimFace', 'RimFace'), 'dark': ('RimDark', 'RimLip')}[cap]
        cr = Wp.get('cap_r', 0.034)
        lathe([(0.0, 0.100), (cr * 0.6, 0.099), (cr * 0.88, 0.095), (cr, 0.090)], centre[0], 36)
        lathe([(cr, 0.090), (cr + 0.006, 0.088), (cr + 0.006, 0.084)], centre[1], 36)
        lathe([(cr + 0.006, 0.084), (cr + 0.008, 0.076), (cr + 0.01, 0.05)], 'RimDark' if cap == 'silver' else 'RimLip', 36)
        for k in range(Wp.get('lugs', 5)):
            a = math.pi / 2 + k * math.tau / Wp.get('lugs', 5)
            old = set(bm.faces)
            res = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.011, radius2=0.011, depth=0.024)
            vs = res['verts']
            bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'X'))
            bmesh.ops.translate(bm, verts=vs, vec=(0.062 * math.cos(a), 0.084, 0.062 * math.sin(a)))
            for f in bm.faces:
                if f not in old: f.material_index = SLOT['Lug']
        bm.from_mesh(face)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return bm

    scale = S['R'] / 0.362
    xr, xf = S['wb']
    out = []
    for name, x, y in (('wheel_FL', xf, 1), ('wheel_FR', xf, -1), ('wheel_RL', xr, 1), ('wheel_RR', xr, -1)):
        bm = wheel_bm()
        if y < 0:
            bmesh.ops.scale(bm, vec=(1, -1, 1), verts=bm.verts)
            bmesh.ops.reverse_faces(bm, faces=bm.faces)
        bmesh.ops.scale(bm, vec=(scale, scale, scale), verts=bm.verts)
        me = bpy.data.meshes.new(f'{cid}_{name}'); bm.to_mesh(me); bm.free()
        for m in MATS: me.materials.append(mats[m])
        for p in me.polygons: p.use_smooth = p.material_index in (SLOT['Tire'], SLOT['RimFace'], SLOT['TireWall'], SLOT['RimLip'], SLOT['Disc'])
        ob = bpy.data.objects.new(name, me)
        ob.location = (x, y * S['track'], S['R'])
        coll.objects.link(ob)
        out.append(ob)
        # Caliper: a block arcing round the disc edge, behind the spokes (it stays put as the wheel spins)
        cb = bmesh.new()
        span = Wp.get('caliper_f' if name[-2] == 'F' else 'caliper_r', (20, 95))
        a0, a1, steps = math.radians(span[0]), math.radians(span[1]), 12
        r0, r1, d0, d1 = (rr - 0.115) * scale, (rr - 0.046) * scale, -0.07 * y, -0.004 * y
        rows = []
        for i in range(steps + 1):
            a = a0 + (a1 - a0) * i / steps
            c, s_ = math.cos(a), math.sin(a)
            rows.append([cb.verts.new((r * c, dd, r * s_)) for r in (r0, r1) for dd in (d0, d1)])
        for ra, rb in zip(rows, rows[1:]):
            for i0, i1 in ((0, 1), (1, 3), (3, 2), (2, 0)):
                cb.faces.new((ra[i0], ra[i1], rb[i1], rb[i0]))
        cb.faces.new((rows[0][0], rows[0][2], rows[0][3], rows[0][1])); cb.faces.new((rows[-1][0], rows[-1][1], rows[-1][3], rows[-1][2]))
        bmesh.ops.recalc_face_normals(cb, faces=cb.faces)
        cme = bpy.data.meshes.new(f'{cid}_caliper_{name[-2:]}'); cb.to_mesh(cme); cb.free()
        cme.materials.append(mats['Caliper'])
        cal = bpy.data.objects.new(f'caliper_{name[-2:]}', cme)
        cal.location = ob.location
        coll.objects.link(cal)
    bpy.data.meshes.remove(face)
    return out


# ---------------------------------------------------------------- build / export
def build(cid):
    S = spec(cid)
    sl = S['_T'].get('slab', 0.0)
    xr, x_lo = S['wb'][0], min(S['ztop'])
    # full slab sides back to the rear axle, easing off so the tail tapers in above the bumper
    SLAB['g'] = lambda x: sl * max(0.25, min(1.0, (x - x_lo) / max(0.1, xr - x_lo)))
    SLAB['rail'] = S['_T'].get('roof_rail', 0.016)  # painted roof edge left above the side glass
    SLAB['valley'] = S['_T'].get('valley', False)
    SLAB['ledge'] = S['_T'].get('ledge', 0.0)
    name = f'Fleet_{cid}'
    old = bpy.data.collections.get(name)
    if old:
        for o in list(old.objects): bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(old)
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    mats = v3_materials(S)
    body, cutter = build_body_v3(cid, S, coll, mats)
    if S['_T'].get('sculpt') is not None:
        bake_subdivision(body, S['_T'].get('sculpt_levels', 2))
        sculpt(body, S['_T']['sculpt'])
        # one more smoothing level over the sculpted shell, ahead of the arch and opening cuts
        sub = body.modifiers.new('Subdivision', 'SUBSURF'); sub.levels = sub.render_levels = 1
        body.modifiers.move(len(body.modifiers) - 1, 0)
    openings(cid, S, coll, mats, body)
    wheels_v3(cid, S, coll, mats)
    bpy.context.view_layer.update()
    F['build_details'](cid, S, coll, mats, body)
    details_v3(cid, S, coll, mats, body)
    F['build_interior'](cid, S, coll, mats)
    if S.get('cabrio'):
        F['build_cabrio'](cid, S, coll, mats)
        # flatter, longer headrest fairings and taller hoops than the fleet's
        hx, hz = S['_T'].get('hump', (1.0, 1.0))
        ws = bpy.data.objects.get(f'{cid}_Windscreen')
        if ws:  # clearer screen in a slim gloss-black frame
            ws.data.materials[0] = material('V3 Screen Glass', (0.02, 0.025, 0.03), 0.0, 0.03, 0.0, alpha=0.5)
            ws.data.materials[1] = mats['RoofBlack']
        for o in coll.objects:
            if '_Hump_' in o.name:
                vs = o.data.vertices
                cx = sum(v.co.x for v in vs) / len(vs); cz = sum(v.co.z for v in vs) / len(vs)
                for v in vs: v.co.x = cx + (v.co.x - cx) * hx; v.co.z = cz + (v.co.z - cz) * hz
            if '_Hoop_' in o.name:
                vs = o.data.vertices
                z0 = min(v.co.z for v in vs)
                for v in vs: v.co.z = z0 + (v.co.z - z0) * S['_T'].get('hoop_h', 1.0)
    return coll


def export(cid, path):
    F['show_only'](cid)
    coll = bpy.data.collections[f'Fleet_{cid}']
    bpy.ops.object.select_all(action='DESELECT')
    for o in coll.objects:
        if 'Cutter' in o.name: continue
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(o for o in coll.objects if o.name.endswith('_Body'))
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_apply=True, export_yup=True,
                              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6,
                              export_draco_position_quantization=14, export_draco_normal_quantization=10,
                              export_cameras=False, export_lights=False)


# ---------------------------------------------------------------- studio sheet
def studio():
    """Soft white studio lighting rendered with Cycles on the GPU. The film is transparent and the
    floor only catches shadows, so the sheet composer can lay the car on the targets' backdrop."""
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for kind in ('OPTIX', 'CUDA'):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            for d in prefs.devices: d.use = d.type == kind
            break
        except Exception:
            continue
    sc.cycles.device = 'GPU'
    sc.cycles.samples = 256
    sc.cycles.use_denoising = True
    sc.render.film_transparent = True
    # Khronos PBR Neutral: made for product shots, it keeps paint colour true and saturated where AgX
    # (with no contrast looks in this build) greys it out
    for vt in ('Khronos PBR Neutral', 'Standard'):
        try:
            sc.view_settings.view_transform = vt
            break
        except TypeError:
            continue
    sc.view_settings.look = 'None'
    sc.view_settings.exposure = -0.75
    print('STEP view', sc.view_settings.view_transform, flush=True)
    # World: a bright ceiling falling off to a grey floor, so the paint carries a soft dark-to-light
    # gradient down its flanks the way a studio cove reflects in a real car.
    w = sc.world
    w.use_nodes = True
    nt = w.node_tree
    bg = next(n for n in nt.nodes if n.type == 'BACKGROUND')
    ramp = nt.nodes.get('V3 Ramp')
    if not ramp:
        tc = nt.nodes.new('ShaderNodeTexCoord')
        sep = nt.nodes.new('ShaderNodeSeparateXYZ')
        ramp = nt.nodes.new('ShaderNodeValToRGB'); ramp.name = 'V3 Ramp'
        maprange = nt.nodes.new('ShaderNodeMapRange')
        maprange.inputs['From Min'].default_value = -1.0
        maprange.inputs['From Max'].default_value = 1.0
        nt.links.new(tc.outputs['Generated'], sep.inputs[0])
        nt.links.new(sep.outputs['Z'], maprange.inputs['Value'])
        nt.links.new(maprange.outputs['Result'], ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
        els = ramp.color_ramp.elements
        # a darker floor and a crisp horizon: the paint picks up a real dark-to-light split down
        # its flanks instead of an even glow
        els[0].position, els[0].color = 0.0, (0.05, 0.05, 0.05, 1)
        els[1].position, els[1].color = 1.0, (1.0, 0.995, 0.985, 1)
        mid = els.new(0.485); mid.color = (0.14, 0.14, 0.14, 1)
        hor = els.new(0.505); hor.color = (0.8, 0.795, 0.785, 1)
        sky = els.new(0.7); sky.color = (0.55, 0.55, 0.545, 1)
    bg.inputs['Strength'].default_value = 0.38
    # Reflections see a separate studio: a dim ceiling and walls with big bright softbox panels (a
    # long overhead strip, side flats, end flats) and a dark floor, so the clearcoat draws crisp
    # light shapes and a hard horizon on the body while the diffuse light stays soft
    if not nt.nodes.get('V3 Glossy Mix'):
        out = next(n for n in nt.nodes if n.type == 'OUTPUT_WORLD')
        tc = nt.nodes.new('ShaderNodeTexCoord')
        sep = nt.nodes.new('ShaderNodeSeparateXYZ')
        nt.links.new(tc.outputs['Generated'], sep.inputs[0])
        def mathn(op, a, b=None, c=None):
            n = nt.nodes.new('ShaderNodeMath'); n.operation = op
            for i, v in enumerate((a, b, c)):
                if v is None: continue
                if isinstance(v, (int, float)): n.inputs[i].default_value = v
                else: nt.links.new(v, n.inputs[i])
            return n.outputs[0]
        X_, Y_, Z_ = sep.outputs['X'], sep.outputs['Y'], sep.outputs['Z']
        def band(v, lo, hi, soft=0.04):  # smooth 0..1 window lo < v < hi
            up = mathn('SMOOTH_MIN', 1.0, mathn('MAXIMUM', 0.0, mathn('DIVIDE', mathn('SUBTRACT', v, lo), soft)), 0.0)
            dn = mathn('MINIMUM', 1.0, mathn('MAXIMUM', 0.0, mathn('DIVIDE', mathn('SUBTRACT', hi, v), soft)))
            return mathn('MULTIPLY', up, dn)
        ay, ax = mathn('ABSOLUTE', Y_), mathn('ABSOLUTE', X_)
        # a bright diffuser ceiling broken by two dark gaps either side of a centre strip
        gaps = mathn('MAXIMUM', band(ay, 0.26, 0.36, 0.02), band(ax, 0.5, 0.6, 0.02))
        overhead = mathn('MULTIPLY', band(Z_, 0.46, 1.1), mathn('SUBTRACT', 1.0, mathn('MULTIPLY', gaps, 0.85)))
        sides = mathn('MULTIPLY', band(Z_, 0.12, 0.42), band(ax, -1.0, 0.55))
        ends = mathn('MULTIPLY', band(Z_, -0.08, 0.4), band(ay, -1.0, 0.42))  # low enough for the nose and tail faces to catch
        panels = mathn('MAXIMUM', mathn('MULTIPLY', overhead, 0.7), mathn('MAXIMUM', sides, ends))
        sky = band(Z_, 0.0, 1.1, 0.03)  # 1 above the horizon, 0 below
        base = mathn('ADD', mathn('MULTIPLY', sky, 0.05), 0.012)
        lum = mathn('ADD', base, mathn('MULTIPLY', panels, 1.0))
        bright = nt.nodes.new('ShaderNodeBackground'); bright.name = 'V3 Glossy Bg'
        nt.links.new(lum, bright.inputs['Color'])
        lp = nt.nodes.new('ShaderNodeLightPath')
        mix = nt.nodes.new('ShaderNodeMixShader'); mix.name = 'V3 Glossy Mix'
        nt.links.new(lp.outputs['Is Glossy Ray'], mix.inputs[0])
        nt.links.new(bg.outputs[0], mix.inputs[1])
        nt.links.new(bright.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs['Surface'])
    nt.nodes['V3 Glossy Bg'].inputs['Strength'].default_value = 3.0
    cyc = bpy.data.objects.get('Cyclorama')
    if cyc: cyc.hide_render = True
    floor = bpy.data.objects.get('V3 Floor')
    if not floor:
        bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 0, 0))
        floor = bpy.context.active_object
        floor.name = 'V3 Floor'
    floor.is_shadow_catcher = True
    # a mid-grey floor in the reflections, like the targets' studio floor in the lower body
    fm = bpy.data.materials.get('V3 Floor') or material('V3 Floor', (0.28, 0.275, 0.27), 0.0, 0.55)
    floor.data.materials.clear(); floor.data.materials.append(fm)
    # Softboxes: a big overhead key and long strips either side, which draw the highlight bands on
    # the paint, plus a low rim from behind.
    def softbox(name, loc, size, energy, aim=(0, 0, 0.5), shape=('RECTANGLE', 1.0)):
        L = bpy.data.objects.get(name)
        if not L:
            L = bpy.data.objects.new(name, bpy.data.lights.new(name, 'AREA'))
            bpy.context.scene.collection.objects.link(L)
        L.data.energy = energy
        L.data.shape = shape[0]
        L.data.size, L.data.size_y = size
        L.location = loc
        L.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    for name in ('Key', 'FillL', 'FillR', 'Rim'):
        L = bpy.data.objects.get(name)
        if L: L.hide_render = True
    # the targets light the car's ends and flanks about as strongly as its top: the faces read
    # brightest and the hood and roof fall to a soft grey, which shows the body's volumes
    softbox('V3 Key', (0.6, 0, 6.0), (5.0, 2.4), 480)
    softbox('V3 Top L', (0.0, 1.5, 4.2), (6.5, 0.45), 420, aim=(0.0, 1.5, 0))
    softbox('V3 Top R', (0.0, -1.5, 4.2), (6.5, 0.45), 420, aim=(0.0, -1.5, 0))
    softbox('V3 Strip L', (0.5, 6.0, 2.9), (6.5, 0.7), 360)
    softbox('V3 Strip R', (0.5, -6.0, 2.9), (6.5, 0.7), 360)
    softbox('V3 Front', (8.0, -3.0, 2.0), (4.0, 2.5), 750, aim=(2.0, 0, 0.45))
    softbox('V3 Back', (-8.0, 3.0, 2.0), (4.0, 2.5), 750, aim=(-2.0, 0, 0.5))


def sheet_look(cid, on):
    """Render-only finish for the sheets, undone before export: metallic flake in the paint under a
    glass-smooth clearcoat, lit lamps (DRLs, tail and centre brake lamps glowing as on the targets)
    and the dark inside of the shell."""
    backface_dark(cid, on)
    m = bpy.data.materials.get(f'Paint {TARGETS[cid]["name"]}')
    if m:
        nt = m.node_tree
        p = bsdf(m)
        for n in [n for n in nt.nodes if n.name.startswith('V3 Flake')]:
            nt.nodes.remove(n)
        if on:
            tex = nt.nodes.new('ShaderNodeTexNoise'); tex.name = 'V3 Flake Noise'
            tex.inputs['Scale'].default_value = 2500.0
            tex.inputs['Detail'].default_value = 0.0
            bump = nt.nodes.new('ShaderNodeBump'); bump.name = 'V3 Flake Bump'
            bump.inputs['Strength'].default_value = 0.06 + 0.12 * TARGETS[cid].get('paint_metal', 0.5)
            nt.links.new(tex.outputs['Fac'], bump.inputs['Height'])
            nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
        p.inputs['Coat Roughness'].default_value = 0.012 if on else 0.02
    glow = {'HeadLamp Fleet': 14.0, 'BrakeLamp Fleet': 9.0, 'CenterBrakeLamp Fleet': 5.0}
    for name, k in glow.items():
        lm = bpy.data.materials.get(name)
        if not lm: continue
        q = bsdf(lm)
        q['v3_rest'] = q.get('v3_rest', q.inputs['Emission Strength'].default_value)
        if name == 'CenterBrakeLamp Fleet':
            q.inputs['Emission Color'].default_value = (1, 0.02, 0.02, 1)
        q.inputs['Emission Strength'].default_value = k if on else q['v3_rest']


def backface_dark(cid, on):
    """While rendering the sheets, shade the inside of the painted shell dark (seen through the glass
    as cabin, as a real car's trimmed interior would be). Removed again before export."""
    m = bpy.data.materials.get(f'Paint {TARGETS[cid]["name"]}')
    if not m: return
    nt = m.node_tree
    out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    p = bsdf(m)
    for n in [n for n in nt.nodes if n.name.startswith('V3 BF')]:
        nt.nodes.remove(n)
    if not on:
        nt.links.new(p.outputs[0], out.inputs['Surface'])
        return
    geo = nt.nodes.new('ShaderNodeNewGeometry'); geo.name = 'V3 BF Geo'
    dark = nt.nodes.new('ShaderNodeBsdfDiffuse'); dark.name = 'V3 BF Dark'
    dark.inputs['Color'].default_value = (0.012, 0.012, 0.013, 1)
    mix = nt.nodes.new('ShaderNodeMixShader'); mix.name = 'V3 BF Mix'
    nt.links.new(geo.outputs['Backfacing'], mix.inputs[0])
    nt.links.new(p.outputs[0], mix.inputs[1])
    nt.links.new(dark.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])


SHEET_VIEWS = {
    # name: camera offset direction (from car centre), height, lens, frame (w, h)
    # the targets were generated as a 70mm product camera, a little above the roofline
    'front': (Vector((0.875, -0.485, 0)), 1.15, 70, (900, 520)),
    'rear': (Vector((-0.92, 0.39, 0)), 1.3, 70, (900, 520)),
    'side': (Vector((0, 1, 0)), 0.62, 200, (1800, 560)),  # long lens: the sheets' side views are near-orthographic
}


def render_views(cid, out_dir, only=None, samples=256):
    F['show_only'](cid)
    studio()
    sc = bpy.context.scene
    sc.cycles.samples = samples
    cam = sc.camera
    coll = bpy.data.collections[f'Fleet_{cid}']
    pts = [o.matrix_world @ Vector(c) for o in coll.objects if o.type == 'MESH' and not o.hide_render for c in o.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    centre = (lo + hi) / 2
    length = hi.x - lo.x
    paths = []
    cams = TARGETS[cid].get('cams', {})
    import json
    fp = os.path.join(REPO, 'blender', 'v3_fit', f'{cid}.json')
    fitted = json.load(open(fp)).get('cams', {}) if os.path.exists(fp) else {}
    for view, (dirv, height, lens, (rw, rh)) in SHEET_VIEWS.items():
        if only and view not in only: continue
        if view in fitted:  # the target's own camera (fit_v3.py), zoomed to frame the car the same way
            c = fitted[view]
            cam.data.type = 'PERSP'; cam.data.sensor_fit = 'HORIZONTAL'; cam.data.sensor_width = 36
            cam.data.shift_x = cam.data.shift_y = 0.0
            sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = rw, rh, 100
            F['look'](cam, Vector(c[:3]), Vector(c[3:6]))
            from bpy_extras.object_utils import world_to_camera_view
            corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
            cam.data.lens = 50.0
            for _ in range(8):
                bpy.context.view_layer.update()
                uv = [world_to_camera_view(sc, cam, p) for p in corners]
                spread = max(max(p.x for p in uv) - min(p.x for p in uv), (max(p.y for p in uv) - min(p.y for p in uv)) * 0.97)
                cam.data.lens *= 0.88 / spread
            bpy.context.view_layer.update()
            uv = [world_to_camera_view(sc, cam, p) for p in corners]
            cam.data.shift_x = (max(p.x for p in uv) + min(p.x for p in uv)) / 2 - 0.5
            cam.data.shift_y = ((max(p.y for p in uv) + min(p.y for p in uv)) / 2 - 0.5) * rh / rw
            path = os.path.join(out_dir, f'{cid}_{view}.png')
            sc.render.filepath = path
            sheet_look(cid, True)
            bpy.ops.render.render(write_still=True)
            sheet_look(cid, False)
            paths.append(path)
            continue
        if view in cams:  # this sheet's own camera for the view: (x, y) direction and height
            (cx, cy), height = cams[view]
            dirv = Vector((cx, cy, 0))
        cam.data.lens = lens
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = rw, rh, 100
        # Pull the camera in or out until the car's bounding box fills ~88% of the frame.
        from bpy_extras.object_utils import world_to_camera_view
        corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
        target = centre + Vector((0, 0, -0.08 if view == 'side' else -0.15))
        dist = 8.0
        cam.data.shift_x = cam.data.shift_y = 0.0
        for _ in range(12):
            pos = centre + dirv.normalized() * dist
            pos.z = height
            F['look'](cam, pos, target)
            bpy.context.view_layer.update()
            uv = [world_to_camera_view(sc, cam, c) for c in corners]
            spread = max(max(p.x for p in uv) - min(p.x for p in uv), (max(p.y for p in uv) - min(p.y for p in uv)) * 0.97)
            dist *= spread / 0.88
        cam.data.shift_x = cam.data.shift_y = 0.0
        bpy.context.view_layer.update()
        uv = [world_to_camera_view(sc, cam, c) for c in corners]
        aspect = rh / rw
        cam.data.shift_x = ((max(p.x for p in uv) + min(p.x for p in uv)) / 2 - 0.5)
        cam.data.shift_y = ((max(p.y for p in uv) + min(p.y for p in uv)) / 2 - 0.5) * aspect
        path = os.path.join(out_dir, f'{cid}_{view}.png')
        sc.render.filepath = path
        sheet_look(cid, True)
        bpy.ops.render.render(write_still=True)
        sheet_look(cid, False)
        paths.append(path)
    return paths


def render_match(cid, out_dir, views=('front', 'rear'), samples=64, scale=2):
    """The 3/4 views through the cameras fit_v3.py recovered from the target sheet, at the sheet's
    view-box size (times scale), so a render lies pixel for pixel over the target."""
    import json
    fit = json.load(open(os.path.join(REPO, 'blender', 'v3_fit', f'{cid}.json')))
    F['show_only'](cid)
    studio()
    sc = bpy.context.scene
    sc.cycles.samples = samples
    cam = sc.camera
    paths = []
    for view in views:
        c = fit['cams'][view]
        w, h = fit['boxes'][view]
        cam.data.type = 'PERSP'
        cam.data.sensor_fit = 'HORIZONTAL'
        cam.data.sensor_width = 36
        cam.data.lens = c[6] / w * 36
        cam.data.shift_x = cam.data.shift_y = 0.0
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w * scale, h * scale, 100
        F['look'](cam, Vector(c[:3]), Vector(c[3:6]))
        path = os.path.join(out_dir, f'{cid}_match_{view}.png')
        sc.render.filepath = path
        sheet_look(cid, True)
        bpy.ops.render.render(write_still=True)
        sheet_look(cid, False)
        paths.append(path)
    return paths


def render_ortho(cid, out_dir):
    """Side view in the target sheet's own pixel scale (lower half of the sheet), for overlaying."""
    F['show_only'](cid)
    studio()
    S = spec(cid)
    T, X, Z, k = S['_T'], S['_X'], S['_Z'], S['_k']
    sc = bpy.context.scene
    cam = sc.camera
    cam.data.type = 'ORTHO'
    cam.data.shift_x = cam.data.shift_y = 0.0
    cam.data.ortho_scale = 1536 * k
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = 1536, 512, 100
    cam.location = (X(768), 20, Z(768))
    cam.rotation_euler = (math.radians(90), 0, math.radians(180))
    sc.cycles.samples = 64
    path = os.path.join(out_dir, f'{cid}_ortho.png')
    sc.render.filepath = path
    sheet_look(cid, True)
    bpy.ops.render.render(write_still=True)
    sheet_look(cid, False)
    cam.data.type = 'PERSP'
    return path
