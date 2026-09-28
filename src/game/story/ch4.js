// 第四章 风雪山隘
// 薇拉在 ch4_start / ch4_vera_talk / ch4_boss_vera 中必然在场。
// 胜利路线二选一：坚守到援军（ch4_last_turn → ch4_boss_retreat）或击败格里姆（ch4_boss_death，会 @set grimm_dead）。
export default {
  ch4_pre: `
# 第四章 战前：雪中的难民车队
@chapter 第四章|风雪山隘
@bg snow_road
@music sad
@fadein
旁白：十天后，北境山道。大雪已经下了三天三夜。
@show elwin left
艾尔文(surprise)：那是……难民的车队？
旁白：翻倒的板车，散落的包袱。雪地上横七竖八地躺着人，大多是老人、女人和孩子。
难民[villager]：救……救命……
@if alive:serin
@show serin farleft
赛琳：别动，我来给你止血！
@end
难民[villager]：我们是从北边村子逃出来的……听说王子还活着，想去南方投奔他……
难民[villager]：黑鹰军说，跟着王子跑的都是叛民……诺德兰的飞龙，就从天上扑下来……
艾尔文(sad)：……他们是想来投奔我的。
@if alive:serin
赛琳：殿下，杀死他们的不是您。是挥刀的人。
@hide serin
@end
难民[villager]：天马骑士里，有个银头发的女队长……她不肯动手，冲着戴角盔的将军喊“他们只是百姓”。
难民[villager]：那将军当着所有人的面，抽了她一鞭子……
艾尔文：一个不肯屠杀百姓的天马骑士……若在战场上遇见她，我想跟她谈谈。
@if alive:nora
@show nora farleft
诺拉：那样的人，在屠夫堆里待不久的。……去试试吧，艾尔文。
@hide nora
@end
@hide all

# 霜牙关要塞
@bg snow_fort
@music tension
旁白：霜牙关要塞。守军早已撤走，只剩几个逃进来避雪的百姓。
@show elwin left
艾尔文：北方的大道，西边的崖道，东边的坡道……三面都能攻上来。
@if alive:nora
@show nora right
诺拉：艾尔文，信鸽！是奥斯温伯爵的回信！
@hide nora
@else
旁白：一只信鸽落在了城垛上。它的腿上，绑着奥斯温伯爵的回信。
@end
艾尔文：“援军已在路上。守住霜牙关，直到听见我的号角。”
@if alive:glenn
@show glenn right
格伦：要塞中央一旦失守，里面的百姓就全完了。殿下，守住那里。
@hide glenn
@end
艾尔文：全员听令！守住要塞中央，撑到援军的号角响起！
@hide all
`,

  ch4_start: `
# 地图开场：霜狼将军与天马骑士队长
@bg map
@show grimm left
格里姆：王子就躲在那座破要塞里。霜狼们，把门给我撞开！
@show vera right
天马骑士队长[vera]：将军，要塞里还有逃难的百姓。
格里姆(angry)：又是你，薇拉。你的天马是用来飞的，不是用来心软的！
格里姆：这是命令——要塞里的活物，一个不留！
天马骑士队长[vera]：……遵命。
@hide all
`,

  ch4_reinf_warn: `
# 增援征兆
@bg map
@if alive:nora
诺拉：山岭那边有翅膀的影子——敌人的援军又来了！
@else
艾尔文：山岭那边有翅膀的影子……敌人的援军又来了！
@end
@hide all
`,

  ch4_turn5: `
# 第 5 回合：格里姆亲自出阵
@bg map
@show grimm right angry
格里姆(angry)：一群废物！都让开——老子亲自去拧下王子的脑袋！
@hide all
`,

  ch4_last_turn: `
# 第 8 回合：再撑一回合
@bg map
@if alive:glenn
格伦：天快亮了……殿下，再撑一阵！援军的号角就要响了！
@else
艾尔文：天快亮了……再撑一阵！援军的号角就要响了！
@end
@hide all
`,

  ch4_vera_talk: `
# 艾尔文与薇拉交谈（入队）
@bg map
@show elwin left
@show vera right
艾尔文：你就是那个不肯屠杀难民的天马骑士？
天马骑士队长[vera]：……维斯特拉的王子。你想说什么？
艾尔文：山道上那些人，只是想活下去。你亲眼看见了。
天马骑士队长[vera]：我看见了。我也看见我的骑士们，把枪刺进了抱着孩子的母亲。
天马骑士队长[vera](sad)：霜翼的誓言，是枪尖只对着拿武器的人。……可那天，我们成了屠夫。
艾尔文：那就别再当屠夫。这座要塞里，也有从山道上逃出来的人。帮我护住他们。
薇拉：……我叫薇拉，霜翼骑士团的队长。——从现在起，大概不是了。
薇拉：这支枪借给你。至少，在这场屠杀结束之前。
@sfx recruit
@hide all
`,

  ch4_boss: `
@bg map
格里姆：南方人的骨头，比雪还脆！
@hide all
`,

  ch4_boss_elwin: `
@bg map
@show grimm right
@show elwin left
格里姆(smile)：王子？瓦尔德的赏金，诺德兰一样认！
艾尔文(angry)：山道上被你们杀死的，都是手无寸铁的百姓！
格里姆：百姓？战场上只有两种人——活人，和死人。
@hide all
`,

  ch4_boss_vera: `
@bg map
@show grimm right angry
@show vera left
格里姆(angry)：薇拉！你这个叛徒！
薇拉：将军，霜翼的誓言是保护弱者。先背叛誓言的，是您。
格里姆(angry)：那我就连你的天马一起，把脖子拧断！
@hide all
`,

  ch4_boss_death: `
@bg map
格里姆：诺德兰的狼……居然……倒在了……南方的雪里……
@set grimm_dead
@hide all
`,

  ch4_boss_retreat: `
# 坚守成功：援军号角响起，格里姆撤退
@bg map
旁白：山谷里，响起了嘹亮的号角声。
@show grimm right angry
格里姆(angry)：号角？……是奥斯温那只老狐狸！撤！全军撤回山那边！
@show elwin left
艾尔文：援军……到了！
@hide all
`,

  ch4_post: `
# 第四章 战后：北境伯爵
@bg snow_fort
@music calm
@fadein
旁白：黎明时分，蓝灰色的军旗越过了山脊。
@show elwin left
@show oswin right
奥斯温：殿下！北境伯爵奥斯温，救驾来迟！
艾尔文：伯爵，这是父王的立储诏书。
奥斯温：……是陛下的笔迹，还有王印。北境的剑，从此只听殿下号令。
@if flag:grimm_dead
奥斯温(smile)：连格里姆都倒在了殿下手里。诺德兰人这回，得好好掂量掂量了。
@end
旁白：伯爵解下背上的长匣，双手捧到艾尔文面前。匣中是一柄白金色的长剑，剑格上刻着鹿角。
奥斯温：白鹿圣剑。开国之王的佩剑，一直由北境代为保管。陛下说过，等殿下能担起王国的那一天，就把它交给您。
艾尔文：……父王连这个，都替我安排好了。
奥斯温：这把剑斩过篡位者，也护过百姓。殿下，拿着它回王都吧。
@sfx item
旁白：艾尔文获得了“白鹿圣剑”。

# 瓦尔德的交易
@if alive:vera
@show vera farright
薇拉：殿下，有件事你必须知道。瓦尔德能调动诺德兰的大军，是因为他开了价。
薇拉：北方三省。只要王子一死，那片土地就归诺德兰。
@hide vera
@else
奥斯温：我的斥候从诺德兰俘虏嘴里撬出了实话。瓦尔德把北方三省许给了诺德兰，换他们出兵。
@end
奥斯温(angry)：北方三省……那是我的领地，是十万人的家！
艾尔文(angry)：他骂父王议和软弱，自己却拿王国的土地，去换一顶王冠。

# 加冕礼与处决
奥斯温：还有，王都传来了消息。三天后，瓦尔德要在王座厅加冕。
奥斯温：加冕礼上，他要公开处决被俘的忠臣。名单上……有王家猎场的总管。
@if alive:nora
@show nora farright surprise
诺拉(surprise)：……我爹？！他还活着？
诺拉(sad)：他还活着……可是三天后……
艾尔文：诺拉。我们会把他救出来。我保证。
@hide nora
@elif dead:nora
艾尔文(sad)：……诺拉的父亲。她到最后，都在等他追上来。
艾尔文：这一次，我替她去接他回家。
@end
艾尔文：伯爵，集结北境的全部兵力。——我们回王都。
@hide all
@fadeout
`,
};
