// 第五章 重返王城
// ch5_boss_glenn / vera / doran / sid 只在对应角色与瓦尔德交战时播放，该角色必然在场。
export default {
  ch5_pre: `
# 第五章 战前：决战前夜
@chapter 第五章|重返王城
@bg war_camp
@music calm
@fadein
旁白：加冕礼前夜。王都城外的山坡上，营火连成了一片。
旁白：王子登上营地中央的木台。北境的士兵、一路追随而来的百姓，都抬起了头。
@show elwin left
艾尔文：北境的将士们，一路追随我的乡亲们，还有陪我走到这里的伙伴们。
艾尔文：一个月前，我从燃烧的王都逃了出来。那时候，我心里只有一件事——复仇。
艾尔文：我想亲手杀了瓦尔德。……现在也一样。
艾尔文：可这一路上，我看见了烧成焦土的村子，雪地里的难民车队，还有被处死在广场上的老臣。
艾尔文：瓦尔德说，父王的仁慈让王国衰弱。可让这个国家流血的，是他。
艾尔文：明天，我要讨回父王的血债。可我们举起剑，不只是为了复仇。
艾尔文：是为了让石溪村的孩子，还能在自己的田里收麦子！是为了把维斯特拉，还给活着的人！
@shake 4
旁白：营火边，爆发出震天的呐喊。
@hide all

# 营火边的伙伴
@show elwin left
@if alive:glenn
@show glenn right
格伦：殿下第一次握剑，是老臣教的。那时候，您还没有剑柄高。
艾尔文(smile)：你每次都这么说。
格伦：明天，老臣走在殿下前面。
艾尔文：不，格伦。我们并肩走。
@hide glenn
@end
@if alive:nora
@show nora right
诺拉：明天我去刑场那边。我爹要是看见我拿着弓来救他，肯定又要骂我不听话。
艾尔文(smile)：那就让他骂个够。
诺拉(smile)：……嗯。让他骂一辈子。
@hide nora
@end
@if alive:serin
@show serin right
赛琳：我会为明天所有的人祈祷……也包括瓦尔德。
艾尔文(surprise)：他也配？
赛琳：不是为他，是为您，殿下。……别让仇恨，把您烧成他那样的人。
艾尔文：……我记住了。
@hide serin
@end
@if alive:doran
@show doran right
多兰：殿下，我罩袍上刮掉鹰徽的地方，缝上了白鹿。
多兰：……针脚很丑。
艾尔文(smile)：比哪面纹章都好看。
@hide doran
@end
@if alive:mira
@show mira right
米拉：账簿我抄了三十份。今晚，城里的朋友会把它们贴满王都的大街小巷。
艾尔文：天亮之后，全城的人都会知道真相。
@hide mira
@end
@if alive:vera
@show vera right
薇拉：明天，天上交给我。诺德兰的飞龙，一只也别想落进王城。
艾尔文：你本可以回北方的。
薇拉：回去继续当屠夫吗？……不了。
@hide vera
@end
@if alive:sid
@show sid right
希德：王子，说正事。王都的下水道我钻了十年，有一条旧渠，直通城门楼底下。
希德：我带几个人先摸进去，把放吊闸的绞盘卸了。你们只管砸门。
艾尔文：……那太危险了。你不怕？
希德(smile)：怕啊。所以记得加钱。
@hide sid
@end
@hide all
旁白：夜深了。艾尔文望着营火，想起了一路上的每一张脸——还在身边的，和没能走到这里的。
@fadeout

# 黎明，城门前
@bg castle_gate
@music tension
@fadein
旁白：黎明。王都的城门，就在眼前。
@if alive:sid
旁白：城门楼里忽然一阵骚乱。吊闸的铁链哗啦作响，却再也放不下来了。
@end
@show elwin left
艾尔文：瓦尔德。……我说过，我会回来的。
@hide all
`,

  ch5_start: `
# 地图开场：王座上的瓦尔德
@bg map
@show valder right
瓦尔德：你还是回来了，艾尔文。比我想的还要快。
瓦尔德：你父亲花了二十年，把王国养成了一头没有牙的羊。你打算拿什么夺回它？一张诏书？一群泥腿子？
瓦尔德：来吧。穿过城门，穿过庭院，走到王座前面来。
瓦尔德：我就在这里等你——像那天晚上，等你父亲一样。
@show elwin left angry
艾尔文(angry)：瓦尔德……这一次，我不会再逃。
@hide all
`,

  ch5_reinf_warn: `
# 增援征兆：大厅两侧的伏兵
@bg map
@if alive:glenn
格伦：大厅两侧的门开了——还有伏兵！殿下，小心侧翼！
@else
艾尔文：大厅两侧的门开了……还有伏兵！
@end
@hide all
`,

  ch5_boss: `
@bg map
瓦尔德：跪下。在新王面前。
@hide all
`,

  ch5_boss_elwin: `
# 最终首领对话
@bg map
@show valder right
@show elwin left angry
瓦尔德：你终于走到这里了。……那天晚上，你父亲最后看的不是我，是门口的你。
艾尔文(angry)：……
瓦尔德：他到死都在担心你。一个连自己都护不住的国王，还能护住谁？
艾尔文(angry)：你骂父王软弱。可你把北方三省卖给了诺德兰，烧了石溪村，还在雪地里屠杀难民！
瓦尔德：割掉一只烂掉的手，才能保住整个身体。等王国重新强大，失去的，我都会拿回来。
艾尔文(angry)：那些死去的人呢？你拿得回来吗？
瓦尔德(smile)：所以呢？你走到这里，是来跟我讲道理的？
艾尔文：不。我是来杀你的。
艾尔文(angry)：为了父王——也为了所有死在你手里的人！
瓦尔德(smile)：很好。这才像他的儿子。——来吧！
@hide all
`,

  ch5_boss_glenn: `
@bg map
@show valder right
@show glenn left
瓦尔德：格伦。那天晚上，你逃得可真快。
格伦：陛下的命令，老臣只做完了一半。
瓦尔德：哦？另一半呢？
格伦(angry)：——把殿下，送回王座！
@hide all
`,

  ch5_boss_vera: `
@bg map
@show valder right
@show vera left
瓦尔德：诺德兰的天马？拿了我的金子，就该替我卖命。
薇拉：霜翼的枪从来不卖。你买下的，只有格里姆那样的人。
@hide all
`,

  ch5_boss_doran: `
@bg map
@show valder right
@show doran left
瓦尔德：守备军的逃兵？连我的鹰徽都敢刮掉。
多兰：刮掉了，缝上了白鹿。……你的鹰，护不住任何人。
@hide all
`,

  ch5_boss_sid: `
@bg map
@show valder right
@show sid left
瓦尔德：贫民窟的老鼠，也配站在王座厅里？
希德(smile)：老鼠也好，泥腿子也好——你看不起的人，今天全都来了。
@hide all
`,

  ch5_boss_defeated: `
# 瓦尔德倒下：提示占领王座
@bg map
@show valder right
瓦尔德：……不可能……我……怎么会……
@hide valder
@if alive:glenn
格伦：殿下，王座！去结束这一切！
@else
艾尔文：父王的王座……就在前面。去结束这一切。
@end
@hide all
`,

  ch5_post: `
# 第五章 战后：灰烬里的王冠
@bg throne_dawn
@music stop
@fadein
旁白：晨光照进了残破的王座厅。瓦尔德靠在王座的台阶下，胸前的黑甲已被鲜血浸透。
@show elwin left
@show valder right
瓦尔德：……咳。你比你父亲……狠。
艾尔文：结束了，瓦尔德。你会在全城百姓面前受审。
瓦尔德(smile)：受审？让那些泥腿子来审我？……你果然是他的儿子。
瓦尔德：你父亲的王冠，就在那堆灰里。那种软弱的东西，我连捡都懒得捡。
瓦尔德：去吧，捡起来。看看你到底继承了什么。
旁白：艾尔文转过头。灰烬里，有一点暗淡的金光。
@sfx sword
@flash red
@shake 6
旁白：寒光一闪——瓦尔德藏在袖中的匕首，直刺王子的咽喉！
@if alive:serin
赛琳(surprise)：殿下，小心！
@end
@sfx hit_heavy
@flash white
旁白：艾尔文的剑，比匕首更快。
瓦尔德：……呵……这顶王冠……很重的……你会……明白……
艾尔文：我早就明白了。
艾尔文(angry)：这一剑，是替父王的。……也是替石溪村，替雪山上的人，替所有被你杀死的人。
@sfx death
@hide valder
旁白：瓦尔德倒在王座的台阶下，再也没有起来。
@music sad
旁白：艾尔文跪在灰烬里，捧起了那顶王冠。它被烧得漆黑，只有白鹿角的纹路，还依稀可辨。
艾尔文(sad)：父王。……我回来了。
@hide all
@fadeout
`,
};
