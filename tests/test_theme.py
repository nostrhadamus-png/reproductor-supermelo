import unittest

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from reproductor import theme  # noqa: E402


class ThemeDataTest(unittest.TestCase):
    def test_todas_las_paletas_tienen_variantes(self):
        self.assertEqual(set(theme.PALETTE_ORDER), set(theme.PALETTES))
        for nombre in theme.PALETTE_ORDER:
            datos = theme.PALETTES[nombre]
            self.assertIn("label", datos)
            for variante in ("light", "dark"):
                if nombre == theme.DEFAULT_PALETTE:
                    self.assertIsNone(datos[variante])
                else:
                    self.assertEqual(
                        set(datos[variante]), set(theme.COLOR_TOKENS), nombre
                    )
                    for token, valor in datos[variante].items():
                        self.assertTrue(theme.valid_hex(valor), f"{nombre}/{variante}/{token}")

    def test_valida_esquema_y_paleta(self):
        for esquema in theme.SCHEMES:
            self.assertEqual(theme.validate_scheme(esquema), esquema)
        for paleta in theme.PALETTE_ORDER:
            self.assertEqual(theme.validate_palette(paleta), paleta)
        self.assertEqual(theme.validate_scheme("sepia"), "system")
        self.assertEqual(theme.validate_scheme(None), "system")
        self.assertEqual(theme.validate_palette("inventada"), "default")
        self.assertEqual(theme.validate_palette(3), "default")

    def test_esquema_efectivo_sigue_al_sistema(self):
        self.assertEqual(theme.effective_scheme("system", True), "dark")
        self.assertEqual(theme.effective_scheme("system", False), "light")
        self.assertEqual(theme.effective_scheme("light", True), "light")
        self.assertEqual(theme.effective_scheme("dark", False), "dark")


class ThemeCssTest(unittest.TestCase):
    def test_genera_css_valido_para_todas_las_combinaciones(self):
        combinaciones = 0
        for paleta in theme.PALETTE_ORDER:
            for esquema in theme.SCHEMES:
                for oscuro in (False, True):
                    css = theme.generate_css(
                        paleta,
                        esquema,
                        system_accent="#3584e4",
                        system_dark=oscuro,
                    )
                    proveedor = Gtk.CssProvider()
                    try:
                        proveedor.load_from_data(css.encode("utf-8"))
                    except Exception as exc:
                        self.fail(f"CSS inválido para {paleta}/{esquema}/{oscuro}: {exc}")
                    self.assertIn("@define-color", css)
                    combinaciones += 1
        self.assertEqual(combinaciones, len(theme.PALETTE_ORDER) * len(theme.SCHEMES) * 2)

    def test_paleta_personalizada_define_todos_los_tokens(self):
        for paleta in theme.PALETTE_ORDER:
            if paleta == theme.DEFAULT_PALETTE:
                continue
            css = theme.generate_css(paleta, "light")
            for token in theme.COLOR_TOKENS:
                self.assertIn(f"@define-color {token} ", css)

    def test_predeterminada_no_pisa_fondos_y_ajusta_texto_del_acento(self):
        css = theme.generate_css("default", "light", system_accent="#3584e4")
        self.assertIn("@define-color accent_fg_color #000000;", css)
        for token in (
            "window_bg_color",
            "view_bg_color",
            "headerbar_bg_color",
            "card_bg_color",
            "accent_bg_color",
            "accent_color",
        ):
            self.assertNotIn(f"@define-color {token} ", css)

    def test_muestra_devuelve_colores_de_la_variante(self):
        fondo_claro, texto_claro, acento_claro = theme.palette_preview(
            "ocean", "light"
        )
        fondo_oscuro, texto_oscuro, acento_oscuro = theme.palette_preview(
            "ocean", "dark"
        )
        self.assertNotEqual(fondo_claro, fondo_oscuro)
        self.assertNotEqual(texto_claro, texto_oscuro)
        self.assertNotEqual(acento_claro, acento_oscuro)
        for color in (fondo_claro, texto_claro, acento_claro):
            self.assertTrue(theme.valid_hex(color))


class ThemeContrastTest(unittest.TestCase):
    def test_contraste_de_todas_las_combinaciones(self):
        fallos = theme.contrast_problems()
        self.assertEqual(
            fallos,
            [],
            "combinaciones por debajo de 4.5:1: "
            + ", ".join(
                f"{paleta}/{variante}/{par}={valor:.2f}"
                for paleta, variante, par, valor in fallos
            ),
        )

    def test_contraste_minimo_de_cada_paleta(self):
        for paleta in theme.PALETTE_ORDER:
            for variante in ("light", "dark"):
                if paleta == theme.DEFAULT_PALETTE:
                    tokens = dict(theme.DEFAULT_REFERENCE[variante])
                    tokens["accent_bg_color"] = "#3584e4"
                    tokens["accent_fg_color"] = theme.best_foreground("#3584e4")
                    tokens["accent_color"] = "#3584e4"
                else:
                    tokens = theme.PALETTES[paleta][variante]
                for fg, bg in theme.CONTRAST_PAIRS:
                    self.assertGreaterEqual(
                        theme.contrast_ratio(tokens[fg], tokens[bg]),
                        theme.MIN_CONTRAST,
                        f"{paleta}/{variante}: {fg} sobre {bg}",
                    )
                if paleta != theme.DEFAULT_PALETTE:
                    for bg in ("window_bg_color", "view_bg_color"):
                        self.assertGreaterEqual(
                            theme.contrast_ratio(tokens["accent_color"], tokens[bg]),
                            theme.MIN_CONTRAST,
                            f"{paleta}/{variante}: accent_color sobre {bg}",
                        )

    def test_texto_negro_o_blanco_siempre_alcanza_aa(self):
        for acento in theme.SYSTEM_ACCENTS:
            fg = theme.best_foreground(acento)
            self.assertGreaterEqual(theme.contrast_ratio(fg, acento), theme.MIN_CONTRAST)

    def test_contraste_de_referencia(self):
        self.assertAlmostEqual(theme.contrast_ratio("#000000", "#ffffff"), 21.0, places=1)
        self.assertAlmostEqual(theme.contrast_ratio("#ffffff", "#ffffff"), 1.0, places=2)
        self.assertTrue(theme.valid_hex("#A1b2C3"))
        self.assertFalse(theme.valid_hex("#12345"))
        self.assertFalse(theme.valid_hex("rojo"))


if __name__ == "__main__":
    unittest.main()
