// 序章 庆典之夜 + 幕间（王都广场的宣告）
// 序章里格伦、赛琳、诺拉必然在场，不需要 @if 保护。
export default {
  prologue: `
# 序章 庆典之夜
@chapter 序章|庆典之夜
@bg festival
@music calm
@fadein
旁白：维斯特拉王国，丰收祭之夜。
旁白：这是国王废除农奴令后的第三个秋天。王都的灯火彻夜不熄，人们为自己田里的麦子举杯。
@show aldric left smile
@show elwin right
艾德里克王(smile)：艾尔文，又从宴席上溜出来了？
艾尔文(smile)：宴席上全是来敬酒的贵族。我宁可到露台上，看广场的篝火。
艾德里克王：……也好。多看看他们的脸。今年的麦子，是他们自己的了。
旁白：国王轻轻咳嗽了几声，扶住了露台的栏杆。
艾尔文(surprise)：父王？您的手好凉。
艾德里克王：人老了，秋风一吹就这样。——艾尔文，明天我有话要对你说。
艾德里克王：有些事，我早该告诉你了。
艾尔文：现在不能说吗？
艾德里克王(smile)：今晚是庆典。就让我再做一晚，只会笑的父亲吧。
@hide all

# 瓦尔德的祝酒
旁白：宴会厅里，乐声停了下来。王国元帅瓦尔德公爵，举起了酒杯。
@show aldric farleft
@show elwin left
@show valder right smile
瓦尔德(smile)：诸位，请举杯。敬我们的国王——
瓦尔德：敬他的仁慈。愿这份仁慈，能替王国挡住北方的刀剑。
旁白：满座的贵族面面相觑。有人低头喝酒，有人藏起了冷笑。
艾德里克王：……也敬你，瓦尔德。这些年，王国的剑一直握在你手里。
瓦尔德：是啊，陛下。一直都是。
@show glenn farright
格伦：……殿下，元帅今晚喝多了。
艾尔文：他只有喝多了，才会说真话。
@hide all
@fadeout
@music stop

# 子夜的警钟
@bg black
@fadein
@wait 40
@sfx warn
@shake 4
旁白：子夜。钟楼上的警钟，忽然响了起来。
@sfx door
@shake 8
旁白：北城门被人从里面打开了。黑鹰旗与诺德兰的狼旗，一同涌进了沉睡的王都。
@music tension
@show glenn right angry
@show elwin left surprise
格伦(angry)：殿下！城门被内应打开了，叛军已经冲进内城！
艾尔文(surprise)：父王呢？！
格伦：陛下还在王座厅——殿下，等等！殿下！
@hide all

# 王座厅
@bg throne_fire
@music boss
@sfx fire
旁白：王座厅燃起了大火。艾尔文撞开大门的那一刻——
@sfx sword
@flash red
@shake 6
旁白：瓦尔德的剑，刺穿了国王的胸膛。
@show elwin left surprise
@show valder right
艾尔文(surprise)：父王——！！
瓦尔德：来得正好，王子殿下。你父亲正要跟你道别。
@show aldric farright sad
艾德里克王(sad)：瓦尔德……为什么……
瓦尔德：别这样看着我，堂兄。你放走农奴，削掉贵族的封地，还向北方的狼低头求和。
瓦尔德：你管这叫仁慈，我管这叫亡国。我只是在王国被你害死之前，替它换一个国王。
艾尔文(angry)：瓦尔德——！
艾德里克王(sad)：艾尔文……别过来……走……活下去……
@sfx death
@hide aldric
旁白：国王倒下了。王冠从他的头上滑落，一路滚进了燃烧的帷幔里。
@sfx burn
@show glenn farleft angry
艾尔文(angry)：放开我，格伦！父王还活着——我要杀了瓦尔德！
格伦：……殿下，恕罪了。
旁白：格伦一把架住王子，硬生生将他拖出了王座厅。
瓦尔德：追。天亮之前，我要看到他的尸体。
@hide all
@fadeout

# 密道
@bg passage
@music tension
@fadein
旁白：王家礼拜堂的祭坛下，有一条通往城外的古老密道。
@show glenn left
@show serin right surprise
赛琳(surprise)：格伦队长！还有……殿下？您的额头在流血！
格伦：赛琳修女？你怎么会在这里？
赛琳：礼拜堂烧起来了，我来抢出圣物……请带上我。我会治伤，路上用得着。
格伦：……跟紧，别出声。
@show elwin farleft angry
艾尔文(angry)：格伦，回去！我命令你回去！
艾尔文(angry)：那是我父亲！你是近卫队长，你发过誓要保护他！
格伦：……是。我发过誓。
艾尔文(angry)：那就让我回去！就算死，我也要死在他身边！
赛琳(sad)：殿下……陛下最后说的，是“活下去”。
艾尔文(sad)：……
@hide all
@fadeout

# 林中
@bg forest_night
@music sad
@fadein
旁白：密道的尽头，是王家猎场的林子。
@show glenn left
@show nora right surprise
诺拉(surprise)：出来了！——格伦队长？还有……艾尔文？你怎么伤成这样？
格伦：诺拉。你父亲呢？
诺拉：爹说，城里要是敲钟，就让我守在旧井边，他去引开巡林的黑鹰兵。……他会追上来的。
诺拉：马备好了。林子里的路我熟，天亮前就能进东边的山。
@hide all
@show elwin left sad
旁白：艾尔文回过头。远处的王都在夜色里燃烧，火光映红了半边天。
艾尔文(sad)：父王……
艾尔文(angry)：瓦尔德。我会回来的。
艾尔文(angry)：我会亲手夺回父王的王冠，让你为今夜流下的每一滴血偿还！
@hide all
@fadeout
@music stop
`,

  interlude_proclaim: `
# 幕间 王都广场的宣告
@bg capital_square
@music enemy
@fadein
旁白：翌日清晨，王都广场。烧焦的旗杆上，升起了黑鹰旗。
@show valder left
@show grimm right
瓦尔德：维斯特拉的子民们。昨夜，我们失去了国王。
瓦尔德：凶手，是他的亲生儿子——王子艾尔文。
瓦尔德：他在庆典之夜弑父篡位，事败之后，与近卫队长格伦一同潜逃。
瓦尔德：献上逆贼首级者，赏金一万。窝藏逆贼者，与逆贼同罪。
旁白：广场上一片死寂。有人低下了头，有人悄悄攥紧了拳头。
格里姆(smile)：说得真好听，公爵大人。答应诺德兰的东西，可别忘了。
瓦尔德：该给你们的，一寸也不会少，格里姆将军。——前提是，那个孩子得死。
格里姆(smile)：那就让我的霜狼们，去嗅一嗅王子的血吧。
@hide all
@fadeout
`,
};
