"""Crea StampaLetraTag.oxt (estensione LibreOffice/OpenOffice) e le icone.

Uso:  python sviluppo/build_oxt.py sviluppo   (poi copia StampaLetraTag.oxt e le icone in programma/)
"""
import os
import sys
import zipfile
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw

APP = sys.argv[1]
SRC = os.path.join(APP, "estensione")
URL = "it.etichette.letratag:stampa"
CTX = ("com.sun.star.text.TextDocument,com.sun.star.sheet.SpreadsheetDocument,"
       "com.sun.star.drawing.DrawingDocument,com.sun.star.presentation.PresentationDocument")


def icon(size):
    s = size * 8
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # etichetta gialla con "LT" stilizzato
    d.rounded_rectangle((s * .05, s * .25, s * .95, s * .75), radius=s * .12,
                        fill=(250, 204, 21, 255), outline=(30, 30, 30, 255), width=max(1, s // 16))
    d.ellipse((s * .14, s * .44, s * .26, s * .56), fill=(30, 30, 30, 255))
    for k, x in enumerate((.36, .52, .68)):
        d.rectangle((s * x, s * .4, s * (x + .1), s * .6), fill=(30, 30, 30, 255))
    return im.resize((size, size), Image.LANCZOS)


os.makedirs(os.path.join(SRC, "icone"), exist_ok=True)
icon(16).save(os.path.join(SRC, "icone", "icona16.png"))
icon(26).save(os.path.join(SRC, "icone", "icona26.png"))
big = icon(256)
big.save(os.path.join(APP, "icona.png"))
big.save(os.path.join(APP, "icona.ico"), sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])

basic = ""
xba = ('<?xml version="1.0" encoding="UTF-8"?>\n'
       '<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">\n'
       '<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Modulo" '
       'script:language="StarBasic">' + escape(basic, {'"': "&quot;"}) + '</script:module>\n')
script_xlb = ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<!DOCTYPE library:library PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "library.dtd">\n'
              '<library:library xmlns:library="http://openoffice.org/2000/library" library:name="LetraTag" '
              'library:readonly="true" library:passwordprotected="false">\n'
              ' <library:element library:name="Modulo"/>\n</library:library>\n')
dialog_xlb = ('<?xml version="1.0" encoding="UTF-8"?>\n'
              '<!DOCTYPE library:library PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "library.dtd">\n'
              '<library:library xmlns:library="http://openoffice.org/2000/library" library:name="LetraTag" '
              'library:readonly="true" library:passwordprotected="false"/>\n')


def prop(name, value):
    return f'<prop oor:name="{name}" oor:type="xs:string"><value>{value}</value></prop>'


item = (prop("URL", URL) + prop("Title", "Stampa su LetraTag") + prop("Target", "_self")
        + prop("Context", CTX))
addons = f'''<?xml version="1.0" encoding="UTF-8"?>
<oor:component-data xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" oor:name="Addons" oor:package="org.openoffice.Office">
 <node oor:name="AddonUI">
  <node oor:name="OfficeToolbarMerging">
   <node oor:name="it.etichette.letratag.barra" oor:op="replace">
    <node oor:name="T1" oor:op="replace">
     {prop("MergeToolBar", "standardbar")}
     {prop("MergePoint", ".uno:ExportDirectToPDF")}
     {prop("MergeCommand", "AddAfter")}
     {prop("MergeCommandParameter", "")}
     {prop("MergeFallback", "AddLast")}
     {prop("MergeContext", CTX)}
     <node oor:name="ToolBarItems">
      <node oor:name="B1" oor:op="replace">
       {item}
       <prop oor:name="ControlType" oor:type="xs:string"><value>ImageButton</value></prop>
      </node>
     </node>
    </node>
   </node>
  </node>
  <node oor:name="AddonMenu">
   <node oor:name="it.etichette.letratag.menu" oor:op="replace">
    {item}
   </node>
  </node>
  <node oor:name="Images">
   <node oor:name="it.etichette.letratag.img" oor:op="replace">
    {prop("URL", URL)}
    <node oor:name="UserDefinedImages">
     {prop("ImageSmallURL", "%origin%/icone/icona16.png")}
     {prop("ImageBigURL", "%origin%/icone/icona26.png")}
    </node>
   </node>
  </node>
 </node>
</oor:component-data>
'''
protocol = """<?xml version="1.0" encoding="UTF-8"?>
<oor:component-data xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" oor:name="ProtocolHandler" oor:package="org.openoffice.Office">
 <node oor:name="HandlerSet">
  <node oor:name="it.etichette.letratag.Gestore" oor:op="replace">
   <prop oor:name="Protocols" oor:type="oor:string-list"><value>it.etichette.letratag:*</value></prop>
  </node>
 </node>
</oor:component-data>
"""
manifest = '''<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="http://openoffice.org/2001/manifest">
 <manifest:file-entry manifest:media-type="application/vnd.sun.star.uno-component;type=Python" manifest:full-path="letratag_componente.py"/>
 <manifest:file-entry manifest:media-type="application/vnd.sun.star.configuration-data" manifest:full-path="ProtocolHandler.xcu"/>
 <manifest:file-entry manifest:media-type="application/vnd.sun.star.configuration-data" manifest:full-path="Addons.xcu"/>
</manifest:manifest>
'''
description = '''<?xml version="1.0" encoding="UTF-8"?>
<description xmlns="http://openoffice.org/extensions/description/2006" xmlns:d="http://openoffice.org/extensions/description/2006" xmlns:xlink="http://www.w3.org/1999/xlink">
 <identifier value="it.etichette.letratag"/>
 <version value="1.2"/>
 <display-name><name lang="it">Stampa su LetraTag</name><name lang="en">Print to LetraTag</name></display-name>
 <dependencies><OpenOffice.org-minimal-version value="3.0" d:name="OpenOffice.org 3.0"/></dependencies>
</description>
'''
out = os.path.join(APP, "StampaLetraTag.oxt")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("META-INF/manifest.xml", manifest)
    z.writestr("description.xml", description)
    z.writestr("Addons.xcu", addons)
    z.write(os.path.join(SRC, "letratag_componente.py"), "letratag_componente.py")
    z.writestr("ProtocolHandler.xcu", protocol)
    z.write(os.path.join(SRC, "icone", "icona16.png"), "icone/icona16.png")
    z.write(os.path.join(SRC, "icone", "icona26.png"), "icone/icona26.png")
print("creato", out)
