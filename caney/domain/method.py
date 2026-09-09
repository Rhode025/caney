"""
TackleMethod — how you are fishing, which is not the same question as what you are in. §20.

Caney 2.x had one axis, `Craft`, and quietly assumed a fly rod at the end of it. Those are
independent: a power boat on Old Hickory is a conventional trip for most people and a fly
trip for some, and a wade on the Caney is nearly always fly but need not be. Collapsing
them made largemouth advice read like trout advice, because the only vocabulary available
was the one the trout pages used.

Method changes the TECHNIQUE and nothing else. It is deliberately not an eligibility gate
and not a scoring input: the fish are where the fish are, and a ledge that holds stripers
at first light holds them for whatever you throw at it. Making method a gate would have
been the easy mistake — it would have started deleting good water from people's plans on
the strength of a preference.
"""


class TackleMethod:
    FLY = "fly"
    CONVENTIONAL = "conventional"
    EITHER = "either"

    ALL = (FLY, CONVENTIONAL, EITHER)
    LABEL = {FLY: "Fly", CONVENTIONAL: "Conventional", EITHER: "Either"}

    #: What a method is willing to be shown. `EITHER` sees both and the technique model
    #: picks whichever the conditions actually favour, rather than defaulting to fly.
    ACCEPTS = {
        FLY: (FLY,),
        CONVENTIONAL: (CONVENTIONAL,),
        EITHER: (FLY, CONVENTIONAL),
    }

    @staticmethod
    def normalise(value):
        v = (value or "").strip().lower()
        if v in TackleMethod.ALL:
            return v
        if v in ("spin", "gear", "bait", "casting", "spinning"):
            return TackleMethod.CONVENTIONAL
        if v in ("flyfishing", "fly_fishing", "fly-rod", "flyrod"):
            return TackleMethod.FLY
        return TackleMethod.EITHER

    @staticmethod
    def accepts(method, technique_method):
        return technique_method in TackleMethod.ACCEPTS.get(
            method or TackleMethod.EITHER, (TackleMethod.FLY, TackleMethod.CONVENTIONAL))
