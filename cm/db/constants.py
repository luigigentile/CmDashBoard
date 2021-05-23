from djchoices import ChoiceItem, DjangoChoices

# The parent category slug hardcoded to control all parts considered to be controllers for the purposes of the
# simple controller strategy
CONTROLLER_SLUG = "controller"


class PinType(DjangoChoices):
    digital = ChoiceItem("digital", "Digital")
    analog = ChoiceItem("analog", "Analog")
    power = ChoiceItem("power", "Power")
    gnd = ChoiceItem("gnd", "GND")
    nc = ChoiceItem("nc", "N/C")
    generic = ChoiceItem("generic", "Generic")


class BusSharing(DjangoChoices):
    """The different ways in which buses on a given interface type can be shared."""

    point_to_point = ChoiceItem("exclusive", "Exclusive (Point-to-point) bus")
    shared = ChoiceItem("shared", "Shared bus")


class InterfaceTypeFunction(DjangoChoices):
    none = ChoiceItem("none", "No Function")
    reset = ChoiceItem("reset", "Reset")
    enable = ChoiceItem("enable", "Enable")
    data_bus = ChoiceItem("data_bus", "Data Bus")
    power = ChoiceItem("power", "Power Bus")
    gnd = ChoiceItem("gnd", "GND")


class InterfaceFunction(InterfaceTypeFunction):
    inherit = ChoiceItem("inherit", "Inherit from interface type")


class DBAncillaryType(DjangoChoices):
    """Ancillary types that are valid to set in the database

    There are additional ancillary types that only make sense to be set on automatically created objects."""

    decoupling_capacitor = ChoiceItem("decoupling_capacitor", "Decoupling Capacitor")
    series_resistor = ChoiceItem("series_resistor", "Series Resistor")
    series_capacitor = ChoiceItem("series_capacitor", "Series Capacitor")
    pull_up_resistor = ChoiceItem("pull_up_resistor", "Pull-up Resistor")
    pull_up_capacitor = ChoiceItem("pull_up_capacitor", "Pull-up Capacitor")
    pull_down_resistor = ChoiceItem("pull_down_resistor", "Pull-down Resistor")
    pull_down_capacitor = ChoiceItem("pull_down_capacitor", "Pull-down Capacitor")
    ferrite_bead = ChoiceItem("ferrite_bead", "Ferrite Bead")
    custom = ChoiceItem("custom", "Custom")


class AncillaryType(DBAncillaryType):
    """All ancillary types, both those that can be set in the db, and ones that only get set automatically."""

    connector = ChoiceItem("connector", "Connector")


# This map determins which category slug belong to which ancillary types.
ANCILLARY_TYPE_MAP = {
    AncillaryType.ferrite_bead: "ferrite-bead",
    AncillaryType.decoupling_capacitor: "non-polarised-capacitor",
    AncillaryType.series_capacitor: "non-polarised-capacitor",
    AncillaryType.series_resistor: "resistor",
    AncillaryType.pull_up_resistor: "resistor",
    AncillaryType.pull_up_capacitor: "non-polarised-capacitor",
    AncillaryType.pull_down_resistor: "resistor",
    AncillaryType.pull_down_capacitor: "non-polarised-capacitor",
}


class AncillaryTarget(DjangoChoices):
    interface: str = ChoiceItem("interface", "Interface")
    interface_type: str = ChoiceItem("interface_type", "InterfaceType")
    interface_family: str = ChoiceItem("interface_family", "InterfaceFamily")


class ConnectionType(DjangoChoices):
    custom: str = ChoiceItem("custom", "Custom connection")
    series: str = ChoiceItem("series", "Connected in series")
    parallel: str = ChoiceItem("parallel", "Connected in parallel")


class DBAncillaryAppliesTo(DjangoChoices):
    """Determines what entity an ancillary applies to. This set is limited to the ones that can be set in the db.

    There are additional cases that only apply to automatically created ancillaries.

    Bus ancillaries apply to a bus as a whole, are only added once on a bus, and cannot have timing constraints.
    Interface ancillaries apply to an interface pin of an interface, and can have timing constraints.
    Pin ancillaries apply to component pins regardless of interfaces being picked on them, can have timing constraints.
    """

    bus = ChoiceItem("bus", "Bus")
    interface = ChoiceItem("interface", "Interface")
    pins = ChoiceItem("pins", "Pins")


class AncillaryAppliesTo(DBAncillaryAppliesTo):
    """Determines what entity an ancillary applies to.

    Includes cases that a user can set in the db, as well as extra ones that only make sense for automatically
    created ancillaries.

    Board ancillaries apply to a board, and can contain multiple buses.
    """

    board = ChoiceItem("board", "Board")


class AncillaryConnectionRole(DjangoChoices):
    """Describes the role of ancillary connection, explaining what it should connect to.

    Input: connects to the target pin on the parent component, or to outputs of previous ancillaries.
    Output: connects to the wider circuit, or acts as inputs to further ancillaries.
    Vref: connects to the reference voltage of the target
    GNDref: connects to the reference gound of the target.
    """

    input = ChoiceItem("input", "Input")
    output = ChoiceItem("output", "Output")
    v_ref = ChoiceItem("v_ref", "Vref")
    gnd_ref = ChoiceItem("gnd_ref", "GNDref")


OPERATOR_SYMBOLS = {
    "exact": "{field} = {value}",
    "iexact": "{field} ~= {value}",
    "contains": "{field} = …{value}…",
    "icontains": "{field} ~= …{value}…",
    "lt": "{field} < {value}",
    "lte": "{field} ≤ {value}",
    "gt": "{field} > {value}",
    "gte": "{field} ≥ {value}",
}


class FilterOperator(DjangoChoices):
    exact = ChoiceItem("exact", "Exact match")
    iexact = ChoiceItem("iexact", "Exact match (ignore case)")
    contains = ChoiceItem("contains", "Contains")
    icontains = ChoiceItem("icontains", "Contains (ignore case)")
    lt = ChoiceItem("lt", "Less than")
    lte = ChoiceItem("lte", "Less than or equal to")
    gt = ChoiceItem("gt", "Greater than")
    gte = ChoiceItem("gte", "Greater than or equal to")


class AncillaryOperator(DjangoChoices):
    exact = ChoiceItem("exact", "Exact match")
    closest = ChoiceItem("closest", "Closest possible value")
    closest_larger = ChoiceItem("closest_larger", "Closest possible larger value")
    closest_smaller = ChoiceItem("closest_smaller", "Closest possible smaller value")


PIN_COLORS = {
    PinType.digital: "#0C4CCC",
    PinType.power: "#CC1F1F",
    PinType.gnd: "black",
    PinType.analog: "#0DA349",
    PinType.nc: "#888888",
}


class BlockAttribute(DjangoChoices):
    """These are the fixed attributes that are allowed to be used for queries on blocks.

    Note: the name used here has to be the name of the actual django field!
    """

    none = ChoiceItem("", "None")
    name = ChoiceItem("name", "Name")
    part_number = ChoiceItem("part_number", "Part Number")
    manufacturer = ChoiceItem("manufacturer", "Manufacturer")
