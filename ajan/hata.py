"""Panele HTTP koduyla dönen hata."""


class Hata(Exception):
    def __init__(self, kod, mesaj):
        super().__init__(mesaj)
        self.kod = kod
        self.mesaj = mesaj


class Mesgul(Hata):
    def __init__(self, mesaj="Bu ortamda süren bir işlem var, bitmesini bekleyin."):
        super().__init__(409, mesaj)
