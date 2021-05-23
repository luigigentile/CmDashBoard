import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Union

from cm.data import schemas, serializable
from cm.exceptions import ValidationError

NET_REGEX = r"(?:(?P<name>[a-zA-Z0-9_-]+)\: )?(?P<nodes>[0-9a-zA-Z-\.]+)"


@dataclass
class Net(serializable.Serializable):
    SCHEMA = schemas.NET_SCHEMA
    name: str = ""
    nodes: List[str] = field(default_factory=list)

    @classmethod
    def from_string(cls, raw_net: str) -> "Net":
        """Factory method to create a net from a raw net string.

        Nets are essentially a list of nodes, with an optional name.

        Example:
            >>> Net.from_string('NET_NAME: R.1-C.1-ATMEGA.D7')
            Net(name='NET_NAME', nodes=['R.1', 'C.1', 'ATMEGA.D7'])
        """

        m = re.fullmatch(NET_REGEX, raw_net)
        if not m:
            raise ValueError(f"Invalid net {raw_net}")
        name, nodes = m.group("name"), m.group("nodes").split("-")

        return cls(name=name or "", nodes=nodes,)

    @classmethod
    def from_data(cls, raw_data: Union[str, Dict[str, Any]], quote_string: str = "") -> "Net":  # type: ignore
        # Net needs an overwritten from_data method because we allow parsing it from a string
        # instead of a dict, for simplicity.
        if isinstance(raw_data, str):
            return cls.from_string(raw_data)
        return super().from_data(raw_data)

    @classmethod
    def match_net(cls, available_nets: List["Net"], net_str: str) -> "Net":
        """Match a net string to an existing list of available nets.

        Net strings are inherently ambiguous:
            - They can, but don't have to, specify a name
            - If they don't specify a name, any node on the net will do

        So, to match a net string we do the following:
            - If a name is specified, look for an available net with that name
            - If no name is specified, go through the node list and find the
            first net where any nodes match.

        The net string here is expected to look like "NET_NAME" or "NODE_NAME",
        but we allow full net strings (NET_NAME: NODE-NODE-...) as well.

        If a full net name is given, we'll raise an exception if not all nodes match.
        This is because the expectation here is that net_str simply identifies an existing net.
        If net_str specifies extra nodes, there is likely a mistake in the spec.
        """
        # The identifier passed in here can be one or many nodes, or it can be just the name of a net,
        # we need to distinguish that here
        if ":" not in net_str and "-" not in net_str:
            # The identifier is either a net name or a single node
            for net in available_nets:
                if net.name == net_str:
                    # The identifier matches a net name, return it directly.
                    return net
                if net_str in net.nodes:
                    # The identifier matches a single node, return it directly.
                    return net
            else:
                # We got a name or a single node but couldn't find it, that's an error.
                raise ValidationError(
                    f"Cannot find matching net for identifier {net_str}!"
                )
        else:
            # The identifier is a full net, in which case we need to do more processing
            new_net = Net.from_string(net_str)

        for net in available_nets:
            if new_net.name == net.name:
                return net
                # we return net even though it might be that new_net had more nodes than net

            new_nodes = set(new_net.nodes)
            existing_nodes = set(net.nodes)
            matching_nodes = new_nodes.intersection(existing_nodes)

            if matching_nodes and matching_nodes != new_nodes:
                extra_nodes = new_nodes - matching_nodes
                raise ValidationError(
                    f"Net identifier {net_str} matches net {net.name} "
                    f"but has extra nodes {', '.join(sorted(extra_nodes))}. "
                    f"Please make sure {net.name} is fully defined."
                )
            elif matching_nodes:
                return net
        else:
            raise ValidationError(f"Cannot find matching net for identifier {net_str}!")
