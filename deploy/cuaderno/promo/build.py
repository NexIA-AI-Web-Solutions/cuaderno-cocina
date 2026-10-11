"""Build the public comparison and a paginated print source from one data file."""
import json
import re
import shutil
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / 'comparison.json').read_text())
OUT = ROOT / 'generated'
OUT.mkdir(exist_ok=True)
for name in ('receta.png', 'reservas.png'):
    shutil.copyfile(ROOT/'assets'/name, OUT/name)

def row(item):
    cells = ''.join('<td class="no"><span aria-label="No incluido">—</span></td>' if v is None else '<td class="yes"><span class="check" aria-hidden="true">✓</span>' + escape(v) + '</td>' for v in item['values'])
    return '<tr data-feature="' + item['id'] + '"><th scope="row">' + escape(item['title']) + '<small>' + escape(item['detail']) + '</small></th>' + cells + '</tr>'

def group(g, title=True):
    return ('<tr class="group"><th colspan="4">' + escape(g['title']) + '</th></tr>' if title else '') + ''.join(row(r) for r in g['rows'])

source = (ROOT / 'page-template.html').read_text()
body = re.search(r'<tbody>(.*?)</tbody>', source, re.S).group(1)
benefits = re.findall(r'<tr class="benefit">.*?</tr>', body, re.S)
assert len(benefits) == 2
source = re.sub(r'<tbody>.*?</tbody>', '<tbody>' + benefits[0] + ''.join(group(g) for g in DATA['groups']) + benefits[-1] + '</tbody>', source, count=1, flags=re.S)
source = source.replace('Más control en cada paso de tu cocina', 'Tu cocina organizada. Revisiones automáticas. Tú decides.')
source = source.replace('Empieza por tus recetas, organiza los servicios y conecta la cocina con el almacén. Cada plan incluye todo lo del anterior.', 'Recetas, servicios y compras conectados, con trabajadores digitales según tu edición. Programa revisiones y aprueba los cambios. Cada plan incluye todo lo del anterior.')
source = source.replace('A4 en color · La misma comparativa de esta página', '4 páginas · A4 en color · Texto seleccionable · Actualizado el ' + DATA['updated'])
source = source.replace('href="/cuaderno-cocina/video/Cuaderno-Cocina-Planes.pdf"', 'href="/cuaderno-cocina/video/Cuaderno-Cocina-Planes.pdf?v=20261011-workers-v2"')
notes = '<div class="plan-notes">' + ''.join('<p>' + escape(n) + '</p>' for n in DATA['notes']) + '<p>Actualizado el ' + DATA['updated'] + '.</p></div>'
source = re.sub(r'<div class="plan-notes">.*?</div>', notes, source, count=1, flags=re.S)
# The printable PDF has its own page layout. Keep the video and public page shell.
(OUT / 'index.html').write_text(source)

header = '<thead><tr><th scope="col">Funcionalidad</th><th scope="col">Esencial<small>500 € + 17 €/mes</small></th><th scope="col">Profesional<small>1.000 € + 20 €/mes</small></th><th scope="col">Integral<small>1.500 € + 30 €/mes</small></th></tr></thead>'
lead = ['Tu recetario, tus raciones y tus costes en un mismo lugar.', 'De las reservas a las cantidades y la preparación del servicio.', 'Conecta lo que necesitas cocinar con lo que tienes y lo que recibes.', 'Revisiones programadas con datos de tu cuaderno. Los cambios requieren tu aprobación.']
page_notes = [DATA['notes'][0:2], [DATA['notes'][0],DATA['notes'][5]], [DATA['notes'][2],DATA['notes'][6]], [DATA['notes'][3],DATA['notes'][4]]]
pages = []
for i,g in enumerate(DATA['groups']):
    addition = ''
    if i == 0:
        addition = '<figure><img src="receta.png" alt="Ficha de receta de demostración"><figcaption>Captura real · Datos de demostración · Receta, ingredientes y coste.</figcaption></figure>'
    elif i == 1:
        addition = '<figure><img src="reservas.png" alt="Reservas de demostración"><figcaption>Captura real · Datos de demostración · Reservas y producción del día.</figcaption></figure>'
    elif i == 2:
        addition = '<aside><h3>Del servicio a la compra revisada</h3><p>Necesidades → Existencias utilizables → Propuesta → Aprobación del borrador</p><p class="separate">Al llegar la mercancía, confirma la recepción para actualizar el stock.</p></aside><div class="contact"><h3>Pide una demostración</h3><p>Descubre qué edición encaja en tu cocina.</p><a href="mailto:alvaro.schwiedop@evocon-solutions.com">alvaro.schwiedop@evocon-solutions.com</a><a href="https://gex-dashboard.hopto.org/cuaderno-cocina/video/">Ver vídeo y comparativa online →</a></div>'
    pages.append('<section class="pdf-page" data-page="'+str(i+1)+'"><div class="content"><div class="eyebrow">CUADERNO COCINA · COMPARATIVA DE EDICIONES</div><h1>'+escape(g['title'])+'</h1><p class="lead">'+lead[i]+'</p><p class="subtitle">'+escape(g['subtitle'])+'</p><table>'+header+'<tbody>'+group(g,False)+'</tbody></table>'+addition+'<div class="notes">'+''.join('<p>'+escape(n)+'</p>' for n in page_notes[i])+'</div></div><footer><span>Actualizado el '+DATA['updated']+' · Cada edición incluye la anterior</span><b>'+str(i+1)+' / 4</b></footer></section>')
html = '<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Cuaderno Cocina · Ediciones y trabajadores digitales</title><style>'+(ROOT/'print.css').read_text()+'</style></head><body>'+''.join(pages)+'</body></html>'
(OUT/'print.html').write_text(html)
print('Generated web table and 4-page print source:',sum(len(g['rows']) for g in DATA['groups']),'feature rows')
