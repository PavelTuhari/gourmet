"""Минимальный писатель формата Roblox XML place (.rbxlx).

Формат — XML-дерево из ``<Item class="...">`` c ``<Properties>``;
файл открывается в Roblox Studio (File → Open from File). Поддержаны
типы свойств, необходимые для сцен planogram3d: Part, SpawnLocation,
Model, Script/LocalScript/ModuleScript (с Luau-исходником),
ProximityPrompt, BillboardGui, TextLabel.

Система координат Roblox: Y — вверх; сцены planogram3d (x, y, высота)
переводятся как (x → X, высота → Y, y → Z).
"""

from typing import List, Optional, Tuple
from xml.sax.saxutils import escape

# токены Enum.Material
MATERIALS = {"Plastic": 256, "SmoothPlastic": 272, "Neon": 288,
             "Wood": 512, "WoodPlanks": 528, "Marble": 784,
             "Concrete": 816, "Granite": 832, "Brick": 848,
             "Metal": 1088, "Ice": 1536, "Glass": 1568}


class Inst:
    """Узел дерева Roblox: класс, свойства, дети."""

    _ref = 0

    def __init__(self, class_name: str, name: str):
        Inst._ref += 1
        self.ref = f"RBX{Inst._ref}"
        self.class_name = class_name
        self.name = name
        self.props: List[str] = [f'<string name="Name">{escape(name)}'
                                 f"</string>"]
        self.children: List["Inst"] = []

    # ----- сериализация свойств ----------------------------------------
    def p_bool(self, name, v):
        self.props.append(f'<bool name="{name}">{"true" if v else "false"}'
                          f"</bool>")
        return self

    def p_float(self, name, v):
        self.props.append(f'<float name="{name}">{v}</float>')
        return self

    def p_int(self, name, v):
        self.props.append(f'<int name="{name}">{v}</int>')
        return self

    def p_token(self, name, v):
        self.props.append(f'<token name="{name}">{v}</token>')
        return self

    def p_string(self, name, v):
        self.props.append(f'<string name="{name}">{escape(v)}</string>')
        return self

    def p_source(self, source: str):
        self.props.append('<ProtectedString name="Source">'
                          f"<![CDATA[{source}]]></ProtectedString>")
        return self

    def p_vec3(self, name, x, y, z):
        self.props.append(f'<Vector3 name="{name}"><X>{x}</X><Y>{y}</Y>'
                          f"<Z>{z}</Z></Vector3>")
        return self

    def p_cframe(self, x, y, z):
        self.props.append(
            f'<CoordinateFrame name="CFrame"><X>{x}</X><Y>{y}</Y><Z>{z}</Z>'
            "<R00>1</R00><R01>0</R01><R02>0</R02>"
            "<R10>0</R10><R11>1</R11><R12>0</R12>"
            "<R20>0</R20><R21>0</R21><R22>1</R22></CoordinateFrame>")
        return self

    def p_color3uint8(self, name, hex_color: str):
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        self.props.append(f'<Color3uint8 name="{name}">'
                          f"{(0xFF << 24) | (r << 16) | (g << 8) | b}"
                          f"</Color3uint8>")
        return self

    def p_color3(self, name, r, g, b):
        self.props.append(f'<Color3 name="{name}"><R>{r}</R><G>{g}</G>'
                          f"<B>{b}</B></Color3>")
        return self

    def p_udim2(self, name, xs, xo, ys, yo):
        self.props.append(f'<UDim2 name="{name}"><XS>{xs}</XS><XO>{xo}</XO>'
                          f"<YS>{ys}</YS><YO>{yo}</YO></UDim2>")
        return self

    def add(self, *children: "Inst") -> "Inst":
        self.children.extend(children)
        return self

    def to_xml(self, indent: int = 1) -> str:
        pad = "\t" * indent
        out = [f'{pad}<Item class="{self.class_name}" referent="{self.ref}">',
               f"{pad}\t<Properties>"]
        out += [f"{pad}\t\t{p}" for p in self.props]
        out.append(f"{pad}\t</Properties>")
        out += [c.to_xml(indent + 1) for c in self.children]
        out.append(f"{pad}</Item>")
        return "\n".join(out)


# ----- фабрики базовых объектов -----------------------------------------
def part(name: str, pos: Tuple[float, float, float],
         size: Tuple[float, float, float], color: str,
         material: str = "SmoothPlastic", transparency: float = 0.0,
         can_collide: bool = True, class_name: str = "Part") -> Inst:
    """Блок: pos — центр (X, Y-вверх, Z), size — габариты в стадах."""
    p = Inst(class_name, name)
    p.p_cframe(*pos)
    p.p_vec3("size", *size)
    p.p_color3uint8("Color3uint8", color)
    p.p_token("Material", MATERIALS.get(material, 256))
    p.p_bool("Anchored", True)
    p.p_bool("CanCollide", can_collide)
    p.p_token("shape", 1)
    p.p_float("Transparency", transparency)
    p.p_token("TopSurface", 0)
    p.p_token("BottomSurface", 0)
    if class_name == "SpawnLocation":
        p.p_bool("Neutral", True)
    return p


def script(name: str, source: str, class_name: str = "Script") -> Inst:
    return Inst(class_name, name).p_source(source)


def prompt(action: str, obj: str, hold: float = 0.5,
           distance: float = 8.0) -> Inst:
    pr = Inst("ProximityPrompt", "Prompt")
    pr.p_string("ActionText", action)
    pr.p_string("ObjectText", obj)
    pr.p_float("HoldDuration", hold)
    pr.p_float("MaxActivationDistance", distance)
    pr.p_bool("RequiresLineOfSight", False)
    return pr


def billboard(text: str, offset_y: float = 3.0, width: int = 220,
              height: int = 44, color=(1, 1, 1)) -> Inst:
    gui = Inst("BillboardGui", "Label")
    gui.p_udim2("Size", 0, width, 0, height)
    gui.p_vec3("StudsOffset", 0, offset_y, 0)
    gui.p_bool("AlwaysOnTop", True)
    gui.p_float("LightInfluence", 0)
    gui.p_float("MaxDistance", 220)
    gui.p_bool("Active", True)
    lbl = Inst("TextLabel", "Text")
    lbl.p_udim2("Size", 1, 0, 1, 0)
    lbl.p_float("BackgroundTransparency", 1)
    lbl.p_string("Text", text)
    lbl.p_bool("TextScaled", True)
    lbl.p_color3("TextColor3", *color)
    gui.add(lbl)
    return gui


def build_place(workspace_children: List[Inst],
                server_scripts: Optional[List[Inst]] = None,
                replicated: Optional[List[Inst]] = None,
                starter_gui: Optional[List[Inst]] = None) -> str:
    """Собрать полный .rbxlx: Workspace + сервисы со скриптами."""
    workspace = Inst("Workspace", "Workspace").add(*workspace_children)
    items = [workspace, Inst("Lighting", "Lighting"),
             Inst("Players", "Players"),
             Inst("Teams", "Teams"),
             Inst("SoundService", "SoundService")]
    rep = Inst("ReplicatedStorage", "ReplicatedStorage")
    if replicated:
        rep.add(*replicated)
    items.append(rep)
    sss = Inst("ServerScriptService", "ServerScriptService")
    if server_scripts:
        sss.add(*server_scripts)
    items.append(sss)
    sg = Inst("StarterGui", "StarterGui")
    if starter_gui:
        sg.add(*starter_gui)
    items.append(sg)

    body = "\n".join(i.to_xml(1) for i in items)
    return (
        '<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" '
        'version="4">\n'
        "\t<External>null</External>\n\t<External>nil</External>\n"
        f"{body}\n</roblox>\n")
