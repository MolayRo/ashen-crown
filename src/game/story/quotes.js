// 阵亡遗言（经典模式）/ 撤退台词（休闲模式）/ 游戏结束
// death_{id} 与 retreat_{id} 播放时该角色必然在场。
export default {
  death_glenn: `
@bg map
格伦(sad)：殿下……老臣……先走一步了……
格伦(sad)：别回头……一直……往前走……
@hide all
`,
  retreat_glenn: `
@bg map
格伦：老骨头不中用了……殿下，恕老臣暂退！
@hide all
`,

  death_nora: `
@bg map
诺拉(sad)：爹……对不起……
诺拉(sad)：这一次……好像……追不上你了……
@hide all
`,
  retreat_nora: `
@bg map
诺拉：可恶，腿上中了一箭……我先撤了！
@hide all
`,

  death_serin: `
@bg map
赛琳(sad)：殿下……请别为我哭……
赛琳(sad)：要一直……朝着有光的地方……走……
@hide all
`,
  retreat_serin: `
@bg map
赛琳：我撑不住了……殿下，请千万小心。
@hide all
`,

  death_doran: `
@bg map
多兰：这一次……我也……没有让开……
@hide all
`,
  retreat_doran: `
@bg map
多兰：……盾裂了。我先退下。
@hide all
`,

  death_sid: `
@bg map
希德(sad)：哈……这笔买卖……亏大了……
希德(sad)：王子……欠我的账……记得……还……
@hide all
`,
  retreat_sid: `
@bg map
希德：打不过就跑——这可是我的看家本事！
@hide all
`,

  death_mira: `
@bg map
米拉(sad)：对不起……殿下……
米拉(sad)：我还有……好多书……没读完……
@hide all
`,
  retreat_mira: `
@bg map
米拉：魔力用光了……我、我先退到后面去！
@hide all
`,

  death_vera: `
@bg map
薇拉(sad)：霜翼的誓言……我……守住了吗……
@hide all
`,
  retreat_vera: `
@bg map
薇拉：天马受伤了……我先撤出战场！
@hide all
`,

  gameover_elwin: `
@bg map
艾尔文(sad)：父王……对不起……我……回不去了……
@fadeout
@music stop
@bg black
@fadein
旁白：王子倒下了。维斯特拉最后的火光，就此熄灭。
`,

  gameover_martha: `
@bg map
玛莎：孩子们……快……往东……跑……
艾尔文(surprise)：玛莎——！
@fadeout
@music stop
@bg black
@fadein
旁白：村长倒下了。失去了主心骨的难民四散奔逃，再也没能渡过黑水河。
`,
};
