// 第二章 断桥伏击 + 幕间（广场处决）
// 希德在 ch2_start / ch2_sid_talk 中必然在场；多兰在 ch2_boss_doran 中必然在场。
export default {
  ch2_pre: `
# 第二章 战前：断桥
@chapter 第二章|断桥伏击
@bg river_bridge
@music tension
@fadein
旁白：两天后，黑水河畔。石溪村的老老少少，跟在王子身后走了整整两天。
@show elwin left
@show martha right
玛莎：殿下，过了黑水河就是柳溪村了……怎么会？石桥断了！
艾尔文：桥是被人炸断的。……对岸插着黑鹰军的旗子。
@hide martha
@if alive:nora
@show nora right
诺拉：北边还有一座窄木桥，南边有片浅滩能蹚过去。可对岸要是有埋伏……
@hide nora
@else
艾尔文：北边还有一座窄木桥，南边的浅滩也能蹚过去……可对岸八成有埋伏。
@end
@if alive:glenn
@show glenn right
格伦：炸断大桥，逼我们走窄路——是个口袋阵。殿下，让老臣打头阵。
艾尔文：……随你。
@hide glenn
@end
@if alive:doran
@show doran right
多兰：……那面旗，是哈根将军的。
艾尔文：你认识他？
多兰：边境守备军的老长官。我的枪，是他手把手教出来的。
@hide doran
@end
@show martha right
艾尔文：玛莎，你带着大家跟在后面。我们先把路清出来——东岸渡口见！
玛莎：老婆子记住了。殿下，千万小心。
@hide all
`,

  ch2_start: `
# 地图开场：桥头守将哈根与红发向导
@bg map
@show hagen left
哈根：果然往东来了。都给老夫听好，桥头一步也不许退！
@show sid right
红发向导[sid]：将军，路我已经带到了。剩下的一半赏钱呢？
哈根：打完这一仗再说。
红发向导[sid]：啧，当兵的赖起账来，跟收过路钱的一个德行……
红发向导[sid](smile)：——说起来，收费站那个箱子，好像没人看着嘛。
@hide all
`,

  ch2_turn3_hint: `
# 第 3 回合：提示与红发向导交谈（希德仍在地图上且未入队时）
@bg map
@if alive:sid & !recruited:sid
@if alive:nora
诺拉：艾尔文，看那个撬箱子的红头发。他不像黑鹰兵，倒像是雇来带路的。
诺拉：雇来的人，就能再雇一次。去跟他谈谈？
@else
艾尔文：那个撬箱子的红头发……不像黑鹰兵，倒像是雇来带路的。去跟他谈谈吧。
@end
@end
@hide all
`,

  ch2_reinf_warn: `
# 增援征兆：北边大路的骑兵
@bg map
@if alive:glenn
格伦：北边大路上起了烟尘——是骑兵！殿下，别让他们冲过木桥！
@else
艾尔文：北边大路上起了烟尘……是骑兵！不能让他们冲过木桥！
@end
@hide all
`,

  ch2_sid_talk: `
# 艾尔文与希德交谈（入队）
@bg map
@show elwin left
@show sid right
红发向导[sid](smile)：哟，王子殿下亲自来抓贼？这箱子可是我先看上的。
艾尔文：箱子你拿走。我只问一句——你知道黑鹰军在追的，都是些什么人吗？
红发向导[sid]：一个逆贼王子，外加……一群走不动路的老头老太太。
艾尔文：是一个被烧光的村子。他们除了身上的衣服，什么都没有了。
红发向导[sid]：……王家的事，关我什么事。
艾尔文：那就别管王家的事。帮我把这些人送过河，工钱我照付。
红发向导[sid](smile)：……先说好，我可是很贵的。我叫希德。
希德(smile)：还有——等你当上国王，欠我的账，得加倍还。
@sfx recruit
@hide all
`,

  ch2_boss: `
@bg map
哈根：老夫守了一辈子边境，还没让谁从面前过去过！
@hide all
`,

  ch2_boss_elwin: `
@bg map
@show hagen right
@show elwin left
哈根：殿下。老夫曾在先王面前宣誓效忠……可军令就是军令。
艾尔文(angry)：你向父王宣过誓，却替杀他的人守桥？
哈根：军人不问对错。——来吧，别指望老夫手下留情！
@hide all
`,

  ch2_boss_doran: `
@bg map
@show hagen right
@show doran left
哈根：多兰？你小子……把鹰徽刮掉了？
多兰：将军。您教过我，枪是用来护住身后的人的。
哈根(angry)：老夫是教过。可老夫没教过你违抗军令！
多兰：石溪村的军令，是烧死一礼拜堂的老人和孩子。……将军，请让开。
哈根：……老夫让不开。来吧，让我看看你的枪练成了什么样！
@hide all
`,

  ch2_boss_death: `
@bg map
哈根：……老夫……终究是老了……先王啊……老夫这就……去向您请罪……
@hide all
`,

  ch2_martha_escape: `
# 玛莎抵达东岸撤离点
@bg map
@show martha right
@show elwin left
玛莎：到了，到对岸了！殿下，大家都过来了！
艾尔文：好！全员撤到东岸！
@hide all
`,

  ch2_post: `
# 第二章 战后：柳溪村
@bg refugee_camp
@music calm
@fadein
旁白：黑水河东岸，柳溪村。石溪村的难民，终于有了落脚的地方。
@show elwin left
@show martha right
玛莎：柳溪村的人答应收留我们了。孩子们今晚，总算能睡个安稳觉。
艾尔文：你们就留在这里吧。前面的路，只会更凶险。
玛莎：……殿下，等您夺回王都，可要回来接我们回家。
艾尔文：我答应你。
@hide all

# 格伦与希德的冲突
@if alive:glenn & alive:sid
@show glenn left
@show sid right
格伦：殿下，那个盗贼靠不住。今天他能为钱给黑鹰军带路，明天就能为钱把我们卖了。
希德：说得好像你们骑士不拿薪水似的。
格伦：近卫骑士拿的是俸禄，守的是誓言。
希德(smile)：誓言？你的誓言，守住你家国王了吗？
@show elwin farleft angry
艾尔文(angry)：希德！
希德：……当我没说。
格伦：不。他说得没错。
旁白：艾尔文攥紧了拳头。他自己也说不清，刚才为什么要替格伦出声。
@hide all
@end

# 审讯官的动向
@show elwin left
村民：殿下！我们在渡口的芦苇丛里，逮到一个黑鹰军的传令兵！他身上带着军令！
艾尔文：……“审讯官摩根，即赴静语修道院，搜查先王遗信。沿途各部，听其调遣。”
艾尔文(surprise)：父王的……信？
@if alive:serin
@show serin right surprise
赛琳(surprise)：静语修道院……本笃院长是我的老师，也是陛下的忏悔神父。
赛琳：陛下每年秋天都去修道院静修。如果陛下留下了什么，一定在院长手里。
@hide serin
@else
艾尔文：静语修道院……本笃院长是父王的忏悔神父。父王每年秋天，都去那里静修。
@end
艾尔文：瓦尔德这么急着找它，信里一定有他害怕的东西。
@if alive:glenn
@show glenn right
格伦：殿下，这也可能是引您上钩的陷阱。
艾尔文：那也得去。——赶在那个审讯官之前。
@hide glenn
@end
艾尔文：天一亮，就去静语修道院。
@hide all
@fadeout
`,

  interlude_square: `
# 幕间 王都广场的处决
@bg capital_square
@music enemy
@fadein
旁白：王都广场。绞刑架前，挤满了被士兵驱赶来的市民。
@show valder left
瓦尔德：贝特朗大人，你侍奉先王三十年。只要在新王的诏书上签个字，今天就能回家。
旁白：白发的老臣抬起头，朝公爵的靴子啐了一口。
瓦尔德：……可惜。先王的仁慈，只教出了一群不识时务的老骨头。
瓦尔德：行刑。
@sfx hit_heavy
@flash red
旁白：人群里响起压抑的抽泣声。没有人敢抬头。
@show morgan right smile
摩根(smile)：公爵大人，您找我？
瓦尔德：先王死前一个月去过静语修道院。有人看见，他把一只封蜡的木匣交给了院长。
瓦尔德：找到那封信。然后，烧了修道院。
摩根：修士们呢？
瓦尔德：修道院里，不需要留下会说话的人。
摩根(smile)：遵命……我最喜欢安静的地方了。
@hide all
@fadeout
`,
};
