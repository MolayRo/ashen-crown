// 第一章 燃烧的边境村
// 条件约定：alive:id = 未阵亡，且已入队或正作为友军在当前地图上。
// 多兰在 ch1_start / ch1_doran_talk 中必然在场（由触发条件保证），其余伙伴台词一律包在 @if alive 里。
export default {
  ch1_pre: `
# 第一章 战前：石溪村的黑烟
@chapter 第一章|燃烧的边境村
@bg village_burning
@music tension
@fadein
旁白：三天后，东部边境。
@show elwin left
@if alive:nora
@show nora right
诺拉：前面就是石溪村了……不对，那不是炊烟。有人在烧村子！
@hide nora
@end
艾尔文(angry)：是黑鹰军……他们在烧石溪村！
@if alive:glenn
@show glenn right
格伦：殿下，绕路吧。他们是冲着您来的，您一露面，就正中他们下怀。
艾尔文(angry)：所以就眼睁睁看着村子烧成灰？
格伦：您是维斯特拉最后的王族。您若死在这里——
艾尔文(angry)：我已经丢下父王一次了，格伦。这一次，我不会再逃。
格伦：……
@hide glenn
@end
@if alive:nora
@show nora right
诺拉：等等，看礼拜堂门口！有个黑鹰兵调转了枪头，一个人挡着自己的同伴。
艾尔文：……他在护着躲进礼拜堂的村民。
@hide nora
@else
艾尔文：礼拜堂门口……那个黑鹰兵调转了枪头，一个人护着躲在里面的村民？
@end
艾尔文：那个人不是敌人。赶到礼拜堂去，我要跟他谈谈。
@if alive:serin
@show serin right
赛琳：村里还有没逃出来的人。殿下，能救一个，是一个。
@hide serin
@end
艾尔文：全员听令——冲进村子！
@hide all
`,

  ch1_start: `
# 地图开场：戈尔德下令烧村，守备军士兵抗命
@bg map
@show gord left angry
戈尔德(angry)：搜！逆贼王子就藏在这一带，给我一户一户地搜！
戈尔德：公爵大人有令——窝藏逆贼者，与逆贼同罪。把这村子烧干净！
黑鹰士兵：队长，村民都躲进礼拜堂了。可是……守备军那个家伙挡在门口。
@show doran right
守备军士兵[doran]：……这里没有王子。只有老人和孩子。
戈尔德(angry)：你是聋了还是瞎了？让开，不然连你一起烧！
守备军士兵[doran]：我当兵，是为了守住这样的村子。不是为了烧它。
戈尔德：好啊。那就先宰了这个叛徒，再烧礼拜堂！
@hide all
`,

  ch1_turn2: `
# 第 2 回合：多兰喊话，村民逃散
@bg map
@if alive:doran & !recruited:doran
守备军士兵[doran]：都别出礼拜堂！只要我还站着，谁也别想进去！
@elif alive:doran
多兰：都别出礼拜堂！只要我还站着，谁也别想进去！
@end
村民：房子烧起来了！别管东西了，抱上孩子往河边跑！
@hide all
`,

  ch1_reinf_warn: `
# 增援征兆：东边道路
@bg map
@if alive:nora
诺拉：东边大路上有马蹄声！追兵的后队要到了！
@else
艾尔文：东边大路上扬起了尘土……追兵的后队要到了！
@end
艾尔文：得在他们赶到之前，拿下那个队长！
@hide all
`,

  ch1_doran_talk: `
# 艾尔文与多兰交谈（入队）
@bg map
@show elwin left
@show doran right
艾尔文：你是守备军的人？为什么要护着这些村民？
守备军士兵[doran]：……你是谁？
艾尔文：艾尔文。黑鹰军要抓的那个“逆贼”。
守备军士兵[doran](surprise)：王子殿下？……他们说，是您杀了国王。
艾尔文(angry)：你信吗？
守备军士兵[doran]：我只信自己的眼睛。我看见黑鹰军在烧村子，看见一个王子冲进来救火。
多兰：我叫多兰，边境守备军的枪兵。胸口的鹰徽，刚刚刮掉了。
多兰：这一仗，我跟您一起打。
@set doran_talked
@sfx recruit
@hide all
`,

  ch1_village_a: `
# 访问民居 A：伤药
@bg map
草药铺的伙计[villager]：您……是来救我们的？
草药铺的伙计[villager]：这瓶伤药是我娘熬的，最后一瓶了。您拿着，别让您的人白白流血。
艾尔文：……谢谢。关好门，火灭之前别出来。
@hide all
`,

  ch1_village_b: `
# 访问民居 B：五百金
@bg map
杂货铺的老板[villager]：王子殿下！这袋钱您拿去——五百金，是我攒了好几年的。
杂货铺的老板[villager]：反正房子也要烧光了。与其便宜了黑鹰军，不如让您买把好剑。
艾尔文：……我会让这些钱，用在该用的地方。
@hide all
`,

  ch1_village_c: `
# 访问民居 C：力量之种
@bg map
年轻的农夫[villager]：这是我爷爷留下的“力量之种”，说是吃下去，能长一身力气……
年轻的农夫[villager]：可我爷爷……刚才被他们……求您，替他报仇！
艾尔文(angry)：我答应你。——可你得先活下去。躲到礼拜堂后面去！
@hide all
`,

  ch1_boss: `
@bg map
戈尔德：哈！又来一个送死的！
@hide all
`,

  ch1_boss_elwin: `
@bg map
@show gord right
@show elwin left
戈尔德(smile)：王子殿下亲自送上门来了？一万金币的脑袋，老子发财了！
艾尔文(angry)：你烧了多少房子，杀了多少人……我要你一样一样还回来！
@hide all
`,

  ch1_boss_death: `
@bg map
戈尔德：怎么会……公爵说……只是个……毛头小子……
@hide all
`,

  ch1_post: `
# 第一章 战后
@bg village_after
@music sad
@fadein
旁白：火熄了。石溪村的一半，只剩下焦黑的木架。
村民：房子没了……过冬的粮食，也全烧光了……
村民：都是因为王子躲在这附近，黑鹰军才来烧村子的！
@show elwin left sad
艾尔文(sad)：……
@show martha right angry
玛莎(angry)：住口，汉斯！放火的是黑鹰军，不是这孩子！
玛莎：王子殿下，我是石溪村的村长玛莎。……谢谢您回来救我们。
艾尔文(sad)：我来晚了。
玛莎：可您来了。那些当官的老爷，可从来没有来过。

# 多兰：入队 / 阵亡 / 离开
@if alive:doran
@show doran farright
玛莎：还有你，守备军的孩子。你一个人挡在礼拜堂门口，一步都没退。
@if !flag:doran_talked
多兰：……我叫多兰，边境守备军的枪兵。鹰徽已经刮掉了。
@end
多兰：殿下，我回不去守备军了。……让我跟着您吧。
艾尔文：好。往后，拜托你了，多兰。
@hide doran
@elif dead:doran
@if flag:doran_talked
艾尔文(sad)：多兰……他到最后，都没让开礼拜堂的门。
@else
玛莎：那位守备军的兵，到死都没让开礼拜堂的门。……我们连他叫什么都不知道。
@end
艾尔文(sad)：把他葬在礼拜堂旁边吧。
@else
玛莎：那位守备军的兵伤得很重。他说要留在村口拖住后面的追兵，叫我们别等他。
@end

@if alive:serin
@show serin farright
赛琳：伤员都安置好了。……可有几个孩子，从刚才起，就一句话也不说。
@hide serin
@end
@hide all

# 艾尔文与格伦的冲突
@if alive:glenn
@show elwin left
@show glenn right
格伦：殿下，此地不宜久留。追兵还会再来，我们天黑前就得动身。
艾尔文(angry)：又是逃。你除了逃，还会说什么？
格伦：殿下——
艾尔文(angry)：那天晚上也是！你为什么不让我回去救父王！
艾尔文(angry)：他还活着！我明明看见，他还在看着我！
格伦：……陛下的伤，已经救不回来了。
艾尔文(angry)：那你至少该让我死在他身边！
格伦：……那是我的决定。殿下要恨，就恨我吧。
@hide elwin
旁白：王子头也不回地走开了。格伦站在焦黑的废墟里，很久没有动。
@if alive:serin
@show serin left
赛琳：格伦队长，您明明有话要说。为什么不告诉殿下？
格伦：……有些话，不该由我来说。
@end
@elif dead:glenn
@show elwin left sad
旁白：村后的山坡上，多了一座新坟。艾尔文在坟前站了很久。
艾尔文(sad)：格伦……那天晚上，你为什么不让我回去？
艾尔文(sad)：我还没来得及问你……你就这样走了。
@end
@hide all

# 玛莎的决定
@show elwin left
@show martha right
玛莎：殿下，我们商量过了。黑鹰军还会再来，石溪村……守不住了。
玛莎：我们打算往东走，过黑水河去投奔亲戚。能不能让我们跟着您一起走？
艾尔文(surprise)：跟着我？我走到哪里，追兵就会跟到哪里。
玛莎：留在这里，也是一样。至少跟着您，我们知道自己在往哪里走。
艾尔文：……好。只要我还活着，就不会再丢下任何人。
@hide all
@fadeout
`,
};
