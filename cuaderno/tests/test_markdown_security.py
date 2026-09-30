"""Security contracts for the native Markdown-to-Vue instruction renderer."""

from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

import pytest

from cookbook.helper.template_helper import render_instructions


class _EmptyIngredients:
    def all(self):
        return []


class _Step:
    def __init__(self, instruction):
        self.instruction = instruction
        self.ingredients = _EmptyIngredients()


class _RenderedHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.start_tags = []
        self.end_tags = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.start_tags.append((tag, dict(attrs)))

    def handle_startendtag(self, tag, attrs):
        self.start_tags.append((tag, dict(attrs)))
        self.end_tags.append(tag)

    def handle_endtag(self, tag):
        self.end_tags.append(tag)

    def handle_data(self, data):
        self.text.append(data)


def _render(markdown):
    html = render_instructions(_Step(markdown))
    parsed = _RenderedHTML()
    parsed.feed(html)
    parsed.close()
    return html, parsed


def _assert_decimal_is_finite(value):
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise AssertionError(f"Vue recibió una expresión en vez de un decimal: {value!r}") from exc
    assert number.is_finite(), f"Vue recibió un decimal no finito: {value!r}"


def _assert_no_executable_attributes(parsed):
    allowed = {
        "scalable-number": {"v-bind:number", "v-bind:factor", "id", "class", "width", "height"},
        "plural-name": {
            "v-bind:amount", "v-bind:factor", ":no-amount", "singular", "plural",
            "id", "class", "width", "height",
        },
    }
    for tag, attrs in parsed.start_tags:
        for name in attrs:
            lowered = name.lower()
            assert not lowered.startswith("on")
            assert not lowered.startswith("v-on")
            assert not lowered.startswith("@")
            assert lowered not in {"v-html", ":is", "srcdoc", "style"}
        if tag in allowed:
            assert set(attrs) <= allowed[tag]
        if "v-bind:number" in attrs:
            _assert_decimal_is_finite(attrs["v-bind:number"])
        if "v-bind:amount" in attrs:
            _assert_decimal_is_finite(attrs["v-bind:amount"])
        if "v-bind:factor" in attrs:
            assert attrs["v-bind:factor"] == "ingredient_factor"


def test_native_renderer_preserves_blockquote_and_legitimate_scale_component():
    html, parsed = _render("> Quote\n\n{{ scale(100) }}")

    assert "blockquote" in [tag for tag, _ in parsed.start_tags]
    assert "Quote" in "".join(parsed.text)
    scalable = [attrs for tag, attrs in parsed.start_tags if tag == "scalable-number"]
    assert scalable == [{"v-bind:number": "100.0", "v-bind:factor": "ingredient_factor"}]
    _assert_no_executable_attributes(parsed)
    assert "<p>&gt; Quote</p>" not in html


@pytest.mark.parametrize(
    ("tag", "attribute", "value"),
    [
        ("scalable-number", "v-bind:number", "NaN"),
        ("scalable-number", "v-bind:number", "Infinity"),
        ("scalable-number", "v-bind:number", "-Infinity"),
        ("plural-name", "v-bind:amount", "NaN"),
        ("plural-name", "v-bind:amount", "Infinity"),
        ("plural-name", "v-bind:amount", "-Infinity"),
        ("scalable-number", "v-bind:number", "1e9999"),
        ("scalable-number", "v-bind:number", "١"),
        ("plural-name", "v-bind:amount", "١"),
    ],
)
def test_non_finite_custom_component_values_are_rejected_as_vue_props(tag, attribute, value):
    if tag == "scalable-number":
        source = f'<{tag} {attribute}="{value}" v-bind:factor="ingredient_factor"></{tag}>'
    else:
        source = (
            f'<{tag} singular="unit" plural="units" {attribute}="{value}" '
            f'v-bind:factor="ingredient_factor" :no-amount="false"></{tag}>'
        )

    _, parsed = _render(source)

    matching = [attrs for parsed_tag, attrs in parsed.start_tags if parsed_tag == tag]
    assert matching, "El saneador puede conservar el componente, pero nunca el prop no finito."
    assert all(attribute not in attrs for attrs in matching)
    _assert_no_executable_attributes(parsed)


@pytest.mark.parametrize(
    "payload",
    [
        '<img src="x" onerror="globalThis.__markdownXss=1">',
        '<a href="javascript:globalThis.__markdownXss=1">link</a>',
        '<script>globalThis.__markdownXss=1</script>',
        '<svg onload="globalThis.__markdownXss=1"><script>globalThis.__markdownXss=1</script></svg>',
        '<iframe srcdoc="<script>globalThis.__markdownXss=1</script>"></iframe>',
        (
            '<scalable-number v-bind:number="\'\'.constructor.constructor(\'globalThis.__markdownXss=1\')()" '
            'v-bind:factor="ingredient_factor" v-on:click="globalThis.__markdownXss=1" '
            '@mouseover="globalThis.__markdownXss=1" v-html="globalThis.__markdownXss=1" '
            ':is="\'script\'"></scalable-number>'
        ),
        (
            '<plural-name singular="unit" plural="units" '
            'v-bind:amount="constructor.constructor(\'globalThis.__markdownXss=1\')()" '
            'v-bind:factor="ingredient_factor" :no-amount="false" '
            '@click="globalThis.__markdownXss=1"></plural-name>'
        ),
        r'{{ "\x3cimg src=x onerror=globalThis.__markdownXss=1\x3e" }}',
        r'{{ "%cimg src=x onerror=globalThis.__markdownXss=1%c"|format(60,62) }}',
        r'{% raw %}{{ "".constructor.constructor("globalThis.__markdownXss=1")() }}{% endraw %}',
    ],
)
def test_script_html_jinja_and_vue_directive_payloads_have_no_executable_structure(payload):
    _, parsed = _render(payload)

    tags = {tag for tag, _ in parsed.start_tags}
    assert tags.isdisjoint({"script", "svg", "iframe", "object", "embed", "template"})
    _assert_no_executable_attributes(parsed)
    for tag, attrs in parsed.start_tags:
        if tag == "a" and "href" in attrs:
            assert not attrs["href"].strip().lower().startswith("javascript:")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e9999"])
def test_scale_never_emits_non_finite_or_zero_for_non_finite_input(value):
    html, parsed = _render('{{ scale("' + value + '") }}')
    assert not any(tag == "scalable-number" for tag, _ in parsed.start_tags)
    assert "No se puede escalar" in html
