# End states

One row per episode in the CSVs; the margin is placed minus the count threshold (strictly more than half).

### softgate35-core: 48 episodes

- placed 34.15 of 61.5 a scene, fill 35.91
- over the threshold 48 / 48; margin median 1, within +-2 of it 30, under by 1-3 0, over by 0-2 30
- margin histogram: 0:9, 1:16, 2:5, 3:5, 4:4, 5:1, 6:1, 7:1, 8:3, 9:2, 10:1
- end reasons: {'declined': 48}
- the item that stopped it: {'soft': 4, 'hard': 37, 'hard+prio': 7}; its dims: {'0.65x0.45x0.25': 19, '0.75x0.56x0.27': 14, '0.55x0.40x0.24': 11, '0.60x0.30x0.25': 3, '0.50x0.40x0.40': 1}
- it fits the largest free floor rectangle flat in 3 episodes (on some face 18); some pool item does flat in 3 (some face 18)
- floor free 0.291 (strips 0.721 of it), free volume above the height map 0.439, highest top 0.950 of the inner height
- soft placed / seen 492 / 496, priority 186 / 193; covered soft 7, priority 12; topples 13
- gap median 5.08 cm, strip share 0.359

| scene | placed/thr | margin | end | next | fits floor | floor free | largest rect | free vol |
|---|---:|---:|---|---|---|---:|---|---:|
| c-c1-s0002 | 21/21 | +0 | declined | hard 0.65x0.45x0.25 | face | 0.32 | 0.58x0.42 | 0.41 |
| c-c1-s0003 | 21/21 | +0 | declined | hard 0.75x0.56x0.27 | no | 0.27 | 0.60x0.26 | 0.48 |
| c-c1-s0004 | 21/21 | +0 | declined | hard 0.75x0.56x0.27 | no | 0.18 | 0.60x0.26 | 0.59 |
| c-c1-s0010 | 21/21 | +0 | declined | hard+prio 0.65x0.45x0.25 | no | 0.25 | 0.76x0.22 | 0.47 |
| c-c1s-s0003 | 21/21 | +0 | declined | hard 0.75x0.56x0.27 | no | 0.29 | 1.00x0.18 | 0.39 |
| c-c1s-s0004 | 21/21 | +0 | declined | hard 0.75x0.56x0.27 | no | 0.29 | 0.62x0.26 | 0.53 |
| c-c1s-s0011 | 21/21 | +0 | declined | hard+prio 0.55x0.40x0.24 | face | 0.41 | 0.70x0.42 | 0.39 |
| c-c1s-s0012 | 21/21 | +0 | declined | hard 0.75x0.56x0.27 | no | 0.32 | 1.10x0.14 | 0.48 |
| c-c2-s0011 | 42/42 | +0 | declined | hard 0.55x0.40x0.24 | face | 0.35 | 0.70x0.42 | 0.50 |
| c-c1-s0001 | 22/21 | +1 | declined | soft 0.50x0.40x0.40 | flat | 0.30 | 0.60x0.44 | 0.54 |
| c-c1-s0007 | 22/21 | +1 | declined | hard 0.55x0.40x0.24 | flat | 0.40 | 0.60x0.48 | 0.41 |
| c-c1-s0008 | 22/21 | +1 | declined | hard 0.65x0.45x0.25 | no | 0.37 | 0.80x0.22 | 0.51 |
| c-c1-s0009 | 22/21 | +1 | declined | hard 0.75x0.56x0.27 | no | 0.31 | 0.54x0.46 | 0.44 |
| c-c1s-s0008 | 22/21 | +1 | declined | hard 0.65x0.45x0.25 | face | 0.37 | 0.88x0.36 | 0.42 |
| c-c1s-s0009 | 22/21 | +1 | declined | hard 0.75x0.56x0.27 | face | 0.37 | 0.60x0.40 | 0.43 |
| c-c1s-s0010 | 22/21 | +1 | declined | hard 0.65x0.45x0.25 | face | 0.28 | 0.70x0.36 | 0.41 |
| c-c2-s0001 | 43/42 | +1 | declined | hard 0.65x0.45x0.25 | no | 0.28 | 0.66x0.26 | 0.50 |
| c-c2-s0003 | 43/42 | +1 | declined | hard+prio 0.75x0.56x0.27 | no | 0.29 | 0.98x0.24 | 0.42 |
| c-c2-s0005 | 43/42 | +1 | declined | hard 0.75x0.56x0.27 | face | 0.31 | 0.84x0.36 | 0.52 |
| c-c2-s0006 | 43/42 | +1 | declined | hard 0.65x0.45x0.25 | no | 0.24 | 0.86x0.22 | 0.45 |
| c-c2-s0007 | 43/42 | +1 | declined | hard 0.65x0.45x0.25 | face | 0.29 | 0.96x0.40 | 0.48 |
| c-c2-s0009 | 43/42 | +1 | declined | hard 0.65x0.45x0.25 | face | 0.27 | 0.60x0.40 | 0.42 |
| c-c2-s0010 | 43/42 | +1 | declined | soft 0.60x0.30x0.25 | flat | 0.24 | 0.70x0.36 | 0.47 |
| c-c2p-s0003 | 43/42 | +1 | declined | hard+prio 0.75x0.56x0.27 | no | 0.29 | 1.48x0.20 | 0.42 |
| c-c2p-s0006 | 43/42 | +1 | declined | hard 0.65x0.45x0.25 | no | 0.23 | 0.54x0.20 | 0.45 |
| c-c1-s0005 | 23/21 | +2 | declined | hard 0.55x0.40x0.24 | face | 0.25 | 0.78x0.30 | 0.49 |
| c-c1-s0006 | 23/21 | +2 | declined | hard 0.75x0.56x0.27 | no | 0.21 | 1.48x0.08 | 0.48 |
| c-c1s-s0001 | 23/21 | +2 | declined | soft 0.60x0.30x0.25 | no | 0.30 | 1.10x0.18 | 0.39 |
| c-c1s-s0005 | 23/21 | +2 | declined | hard 0.55x0.40x0.24 | no | 0.28 | 1.48x0.18 | 0.44 |
| c-c2p-s0002 | 44/42 | +2 | declined | hard 0.75x0.56x0.27 | no | 0.29 | 1.04x0.18 | 0.45 |

### softgate35-core-b: 48 episodes

- placed 35.96 of 61.5 a scene, fill 38.34
- over the threshold 48 / 48; margin median 4, within +-2 of it 19, under by 1-3 0, over by 0-2 19
- margin histogram: 0:7, 1:4, 2:8, 3:4, 4:5, 5:4, 6:3, 7:3, 8:3, 9:2, 10:5
- end reasons: {'declined': 48}
- the item that stopped it: {'soft': 43, 'hard': 3, 'hard+prio': 1, 'soft+prio': 1}; its dims: {'0.65x0.35x0.23': 22, '0.50x0.40x0.40': 19, '0.60x0.30x0.25': 3, '0.75x0.56x0.27': 3, '0.65x0.45x0.25': 1}
- it fits the largest free floor rectangle flat in 1 episodes (on some face 14); some pool item does flat in 3 (some face 21)
- floor free 0.265 (strips 0.781 of it), free volume above the height map 0.420, highest top 0.952 of the inner height
- soft placed / seen 371 / 652, priority 225 / 244; covered soft 0, priority 9; topples 19
- gap median 5.91 cm, strip share 0.364

| scene | placed/thr | margin | end | next | fits floor | floor free | largest rect | free vol |
|---|---:|---:|---|---|---|---:|---|---:|
| b-c1-s0003 | 21/21 | +0 | declined | soft 0.65x0.35x0.23 | face | 0.26 | 0.70x0.26 | 0.46 |
| b-c1-s0004 | 21/21 | +0 | declined | soft 0.60x0.30x0.25 | face | 0.27 | 0.50x0.38 | 0.51 |
| b-c1s-s0003 | 21/21 | +0 | declined | soft 0.65x0.35x0.23 | no | 0.26 | 0.94x0.18 | 0.38 |
| b-c1s-s0006 | 21/21 | +0 | declined | soft 0.50x0.40x0.40 | no | 0.28 | 0.88x0.18 | 0.42 |
| b-c1s-s0010 | 21/21 | +0 | declined | soft 0.65x0.35x0.23 | no | 0.38 | 1.48x0.22 | 0.34 |
| b-c2-s0002 | 42/42 | +0 | declined | soft 0.50x0.40x0.40 | no | 0.35 | 1.16x0.30 | 0.51 |
| b-c2-s0003 | 42/42 | +0 | declined | soft 0.50x0.40x0.40 | no | 0.29 | 0.60x0.40 | 0.47 |
| b-c1s-s0002 | 22/21 | +1 | declined | soft 0.60x0.30x0.25 | flat | 0.30 | 0.70x0.36 | 0.48 |
| b-c2-s0011 | 43/42 | +1 | declined | soft 0.65x0.35x0.23 | no | 0.24 | 0.70x0.22 | 0.57 |
| b-c2p-s0002 | 43/42 | +1 | declined | soft 0.50x0.40x0.40 | no | 0.34 | 1.04x0.22 | 0.45 |
| b-c2p-s0003 | 43/42 | +1 | declined | soft 0.65x0.35x0.23 | face | 0.23 | 0.66x0.34 | 0.40 |
| b-c1-s0006 | 23/21 | +2 | declined | soft 0.50x0.40x0.40 | no | 0.20 | 1.48x0.10 | 0.46 |
| b-c1-s0010 | 23/21 | +2 | declined | soft 0.65x0.35x0.23 | face | 0.30 | 0.62x0.30 | 0.36 |
| b-c1s-s0005 | 23/21 | +2 | declined | soft 0.65x0.35x0.23 | face | 0.29 | 0.90x0.28 | 0.41 |
| b-c2-s0004 | 44/42 | +2 | declined | soft 0.65x0.35x0.23 | face | 0.28 | 0.76x0.32 | 0.48 |
| b-c2-s0005 | 44/42 | +2 | declined | soft 0.65x0.35x0.23 | face | 0.34 | 0.90x0.28 | 0.50 |
| b-c2-s0007 | 44/42 | +2 | declined | soft 0.50x0.40x0.40 | no | 0.28 | 1.36x0.26 | 0.47 |
| b-c2-s0010 | 44/42 | +2 | declined | soft 0.65x0.35x0.23 | face | 0.33 | 0.90x0.26 | 0.39 |
| b-c2-s0012 | 44/42 | +2 | declined | soft 0.50x0.40x0.40 | no | 0.27 | 1.48x0.12 | 0.48 |

### softcap07b-core-a: 48 episodes

- placed 38.25 of 61.5 a scene, fill 36.54
- over the threshold 48 / 48; margin median 6, within +-2 of it 11, under by 1-3 0, over by 0-2 11
- margin histogram: 0:2, 1:6, 2:3, 3:5, 4:2, 5:5, 6:2, 7:5, 8:2, 9:1, 10:15
- end reasons: {'declined': 48}
- the item that stopped it: {'soft': 10, 'hard': 37, 'hard+prio': 1}; its dims: {'0.55x0.40x0.24': 19, '0.65x0.45x0.25': 15, '0.65x0.35x0.23': 7, '0.75x0.56x0.27': 4, '0.60x0.30x0.25': 2, '0.45x0.30x0.20': 1}
- it fits the largest free floor rectangle flat in 1 episodes (on some face 8); some pool item does flat in 1 (some face 8)
- floor free 0.163 (strips 0.869 of it), free volume above the height map 0.434, highest top 0.913 of the inner height
- soft placed / seen 389 / 399, priority 258 / 259; covered soft 1, priority 3; topples 6
- gap median 3.01 cm, strip share 0.234

| scene | placed/thr | margin | end | next | fits floor | floor free | largest rect | free vol |
|---|---:|---:|---|---|---|---:|---|---:|
| a-c1-s0012 | 21/21 | +0 | declined | hard 0.55x0.40x0.24 | no | 0.11 | 1.36x0.08 | 0.57 |
| a-c1s-s0010 | 21/21 | +0 | declined | hard 0.65x0.45x0.25 | no | 0.25 | 1.44x0.24 | 0.60 |
| a-c1-s0002 | 22/21 | +1 | declined | hard 0.65x0.45x0.25 | no | 0.11 | 1.36x0.08 | 0.56 |
| a-c1-s0007 | 22/21 | +1 | declined | hard 0.55x0.40x0.24 | no | 0.11 | 1.36x0.08 | 0.50 |
| a-c1-s0009 | 22/21 | +1 | declined | hard 0.55x0.40x0.24 | no | 0.11 | 1.36x0.08 | 0.53 |
| a-c1s-s0002 | 22/21 | +1 | declined | hard 0.55x0.40x0.24 | face | 0.23 | 0.56x0.42 | 0.43 |
| a-c1s-s0005 | 22/21 | +1 | declined | hard 0.65x0.45x0.25 | no | 0.25 | 1.44x0.24 | 0.54 |
| a-c2p-s0003 | 43/42 | +1 | declined | hard 0.55x0.40x0.24 | no | 0.17 | 1.08x0.14 | 0.43 |
| a-c1-s0003 | 23/21 | +2 | declined | hard 0.75x0.56x0.27 | no | 0.11 | 1.36x0.08 | 0.53 |
| a-c1s-s0003 | 23/21 | +2 | declined | hard 0.65x0.45x0.25 | no | 0.17 | 0.60x0.24 | 0.36 |
| a-c1s-s0009 | 23/21 | +2 | declined | hard 0.65x0.45x0.25 | no | 0.17 | 0.62x0.24 | 0.55 |

### softgate35-hard: 48 episodes

- placed 40.08 of 94.0 a scene, fill 34.83
- over the threshold 17 / 48; margin median -4, within +-2 of it 10, under by 1-3 6, over by 0-2 7
- margin histogram: -6:22, -5:1, -4:2, -3:3, -2:2, -1:1, 0:3, 2:4, 4:1, 6:1, 10:8
- end reasons: {'declined': 48}
- the item that stopped it: {'hard+prio': 1, 'hard': 36, 'soft': 11}; its dims: {'0.55x0.40x0.24': 12, '0.75x0.56x0.27': 10, '0.80x0.60x0.50': 8, '0.65x0.45x0.25': 7, '0.50x0.40x0.40': 4, '0.65x0.35x0.23': 3}
- it fits the largest free floor rectangle flat in 2 episodes (on some face 11); some pool item does flat in 2 (some face 11)
- floor free 0.271 (strips 0.708 of it), free volume above the height map 0.494, highest top 0.936 of the inner height
- soft placed / seen 787 / 798, priority 226 / 227; covered soft 14, priority 19; topples 25
- gap median 3.73 cm, strip share 0.303

| scene | placed/thr | margin | end | next | fits floor | floor free | largest rect | free vol |
|---|---:|---:|---|---|---|---:|---|---:|
| c-hard-s0025 | 48/51 | -3 | declined | soft 0.60x0.30x0.25 | face | 0.28 | 0.66x0.28 | 0.56 |
| c-hard-s0029 | 13/16 | -3 | declined | hard 0.80x0.60x0.50 | no | 0.46 | 1.30x0.30 | 0.50 |
| c-hard-s0047 | 46/49 | -3 | declined | hard 0.80x0.60x0.50 | no | 0.23 | 0.52x0.40 | 0.41 |
| c-hard-s0038 | 35/37 | -2 | declined | soft 0.60x0.30x0.25 | no | 0.28 | 1.72x0.10 | 0.48 |
| c-hard-s0042 | 51/53 | -2 | declined | hard 0.75x0.56x0.27 | no | 0.27 | 1.40x0.16 | 0.45 |
| c-hard-s0048 | 20/21 | -1 | declined | hard 0.55x0.40x0.24 | no | 0.20 | 0.68x0.24 | 0.41 |
| c-hard-s0028 | 50/50 | +0 | declined | soft 0.65x0.35x0.23 | flat | 0.35 | 0.82x0.42 | 0.53 |
| c-hard-s0039 | 28/28 | +0 | declined | hard 0.65x0.45x0.25 | no | 0.27 | 0.46x0.42 | 0.47 |
| c-hard-s0044 | 22/22 | +0 | declined | soft 0.45x0.30x0.20 | no | 0.30 | 0.50x0.20 | 0.72 |
| c-hard-s0004 | 51/49 | +2 | declined | hard 0.65x0.45x0.25 | no | 0.18 | 0.80x0.26 | 0.39 |
| c-hard-s0006 | 23/21 | +2 | declined | hard 0.55x0.40x0.24 | no | 0.20 | 0.42x0.24 | 0.60 |
| c-hard-s0022 | 48/46 | +2 | declined | hard 0.65x0.45x0.25 | face | 0.35 | 0.60x0.36 | 0.43 |
| c-hard-s0043 | 22/20 | +2 | declined | hard 0.75x0.56x0.27 | no | 0.24 | 0.52x0.32 | 0.37 |

### softgate35-hard-b: 48 episodes

- placed 41.42 of 94.0 a scene, fill 34.98
- over the threshold 19 / 48; margin median -4, within +-2 of it 7, under by 1-3 3, over by 0-2 5
- margin histogram: -6:21, -5:3, -4:2, -3:1, -2:2, 0:2, 1:1, 2:2, 3:1, 4:2, 6:1, 8:2, 10:8
- end reasons: {'transport': 1, 'declined': 47}
- the item that stopped it: {'hard': 17, 'soft': 28, 'hard+prio': 3}; its dims: {'0.65x0.35x0.23': 16, '0.80x0.60x0.50': 10, '0.60x0.40x0.40': 8, '0.75x0.56x0.27': 7, '0.50x0.40x0.40': 4, '0.65x0.45x0.25': 2}
- it fits the largest free floor rectangle flat in 5 episodes (on some face 14); some pool item does flat in 7 (some face 20)
- floor free 0.269 (strips 0.722 of it), free volume above the height map 0.487, highest top 0.941 of the inner height
- soft placed / seen 683 / 917, priority 257 / 270; covered soft 8, priority 11; topples 21
- gap median 4.82 cm, strip share 0.337

| scene | placed/thr | margin | end | next | fits floor | floor free | largest rect | free vol |
|---|---:|---:|---|---|---|---:|---|---:|
| b-hard-s0031 | 45/48 | -3 | declined | soft 0.60x0.40x0.40 | no | 0.25 | 0.80x0.30 | 0.50 |
| b-hard-s0022 | 44/46 | -2 | declined | hard 0.55x0.40x0.24 | no | 0.25 | 1.00x0.20 | 0.50 |
| b-hard-s0042 | 51/53 | -2 | declined | soft 0.60x0.40x0.40 | no | 0.28 | 1.16x0.28 | 0.45 |
| b-hard-s0014 | 51/51 | +0 | declined | soft 0.60x0.40x0.40 | flat | 0.27 | 0.72x0.66 | 0.66 |
| b-hard-s0019 | 64/64 | +0 | declined | soft 0.50x0.40x0.40 | no | 0.34 | 0.60x0.40 | 0.38 |
| b-hard-s0043 | 21/20 | +1 | declined | soft 0.65x0.35x0.23 | face | 0.37 | 1.36x0.28 | 0.48 |
| b-hard-s0039 | 30/28 | +2 | declined | hard 0.65x0.45x0.25 | no | 0.21 | 0.34x0.26 | 0.45 |
| b-hard-s0044 | 24/22 | +2 | declined | soft 0.50x0.40x0.40 | no | 0.26 | 0.36x0.24 | 0.73 |
