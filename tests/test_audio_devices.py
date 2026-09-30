import audio_devices as ad

DEVS = [(0, "Sound Mapper", 2), (1, "Microphone (JBL)", 1), (2, "Microphone (Realtek)", 2),
        (3, "Speakers", 0), (4, "Microphone (Realtek)", 2)]


def test_no_name_means_default():
    assert ad.choose(DEVS, "") is None
    assert ad.choose(DEVS, None) is None


def test_finds_the_device_by_exact_name():
    assert ad.choose(DEVS, "Microphone (JBL)") == 1


def test_first_of_duplicate_names_wins():
    assert ad.choose(DEVS, "Microphone (Realtek)") == 2


def test_output_only_devices_are_not_chosen():
    assert ad.choose(DEVS, "Speakers") is None


def test_unplugged_device_falls_back_to_default():
    assert ad.choose(DEVS, "Microphone (Old USB)") is None


class FakeSd:
    def __init__(self, devices, default_host=0):
        self._d = devices
        self._host = default_host

    def query_devices(self, kind=None):
        if kind == "input":
            return {"hostapi": self._host, "name": "x"}
        return self._d


def dev(name, inputs, host):
    return {"name": name, "max_input_channels": inputs, "hostapi": host}


def test_input_names_lists_default_host_inputs_once_each():
    sd = FakeSd([dev("Mic A", 1, 0), dev("Speakers", 0, 0), dev("Mic B", 2, 0), dev("Mic A", 1, 0),
                 dev("Mic A", 1, 1), dev("Mic C", 1, 1)])
    assert ad.input_names(sd) == ["Mic A", "Mic B"]


def test_input_names_is_empty_without_an_input_device():
    class NoInput(FakeSd):
        def query_devices(self, kind=None):
            if kind == "input":
                raise ValueError("No input device")
            return []

    assert ad.input_names(NoInput([])) == []


def test_input_index_uses_the_stored_name():
    sd = FakeSd([dev("Mic A", 1, 0), dev("Mic B", 1, 0)])
    assert ad.input_index("Mic B", sd) == 1
    assert ad.input_index("", sd) is None
    assert ad.input_index("Gone", sd) is None
