"""Panele HTTP koduyla dönen hata."""


class Hata(Exception):
    def __init__(self, kod, mesaj, ayrinti=None):
        super().__init__(mesaj)
        self.kod = kod
        self.mesaj = mesaj
        self.ayrinti = ayrinti  # teknik ayrıntı (komut, çıktı); arayüzde katlanır bölümde gösterilir


class Mesgul(Hata):
    def __init__(self, mesaj="Bu ortamda süren bir işlem var, bitmesini bekleyin."):
        super().__init__(409, mesaj)
