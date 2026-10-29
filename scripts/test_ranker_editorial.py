from ranker_editorial_mkclips import puntuar_ranker_local

def make(rating, hook, payoff, rutina, watchability):
    return {"rating": rating, "hook": hook, "payoff": payoff, "rutina": rutina, "watchability": watchability, "autonomia": watchability, "contexto_suficiente": watchability}

feedback=[]
for _ in range(6): feedback.append(make(5,1,1,0,1))
for _ in range(6): feedback.append(make(1,0,0,1,0))
prefs={"feedback":feedback}
good={"valor_editorial":{"hook":1,"payoff":1,"rutina":0,"watchability":1,"autonomia":1,"contexto_suficiente":1}}
bad={"valor_editorial":{"hook":0,"payoff":0,"rutina":1,"watchability":0,"autonomia":0,"contexto_suficiente":0}}
a=puntuar_ranker_local(good, [], prefs)
b=puntuar_ranker_local(bad, [], prefs)
assert a["activo"] and b["activo"]
assert a["score"] > b["score"], (a,b)
print("OK: ranker local aprende una preferencia editorial simple")
