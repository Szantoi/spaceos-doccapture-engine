"""Szövegréteg-olvasás: a dokumentumban MÁR OTT LÉVŐ szövegréteg kiolvasása.

**Modell nem kell** — ez a második legolcsóbb út a négyből (a táblázatos után).
A négy bemenet négy külön út: ha ezt is a felismerő úton oldanánk meg, a
legolcsóbb esetet fizetnénk meg a legdrágábban.

A csomag két részre bomlik, és ez szándékos:

- `probe` — **MÉRI**, van-e használható szövegréteg (ez az útválasztás bemenete,
  és önállóan futtathatónak kell lennie);
- `reader` — **KIOLVASSA** a réteget geometriával együtt.

A `has_text_layer` a probe verdiktjéből **származik**, nem külön szabályból:
egy igazság ugyanarról a döntésről.
"""
