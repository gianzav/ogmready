from logging import warning
from typing import Any, Callable, Dict, Tuple, Type, TypeVar
import owlready2

type NameWithNamespace = Tuple[str, str]


def resolve_property_name(
    name: str | NameWithNamespace, onto: owlready2.Ontology
) -> str:
    if isinstance(name, str):
        result = name
    else:
        prop, ns = name
        namespace = onto.get_namespace(ns)
        result = namespace[prop].name

    return result


class Mapping:
    def to_owl(self, owl_instance, obj, property_name, onto: owlready2.Ontology):
        raise NotImplementedError

    def from_owl(self, owl_instance, onto: owlready2.Ontology):
        raise NotImplementedError

    def to_query(self, obj, property_name, onto) -> Tuple[str, Any]:
        raise NotImplementedError

    def is_primary_key(self):
        return False


class DataPropertyMapping(Mapping):
    def __init__(
        self,
        target_property: str | NameWithNamespace,
        functional=True,
        primary_key=False,
    ):
        self.target_property = target_property
        self.functional = functional
        self.primary_key = primary_key

    def to_owl(self, owl_instance, obj, property_name, onto):
        target_property = resolve_property_name(self.target_property, onto)
        if self.functional:
            target = getattr(obj, property_name)
        else:
            target = [e for e in getattr(obj, property_name)]

        setattr(owl_instance, target_property, target)

    def from_owl(self, owl_instance, onto):
        target_property = resolve_property_name(self.target_property, onto)
        if self.functional:
            target = getattr(owl_instance, target_property)
        else:
            target = set(getattr(owl_instance, target_property))
        return target

    def to_query(self, obj, property_name, onto):
        if self.functional:
            target = getattr(obj, property_name)
        else:
            target = [e for e in getattr(obj, property_name)]

        return resolve_property_name(self.target_property, onto), target

    def is_primary_key(self):
        return self.primary_key


class ObjectPropertyMapping(Mapping):
    def __init__(
        self,
        relation: str | NameWithNamespace,
        mapper_maker: Callable[[], "Mapper"],
        functional=True,
    ):
        self.relation = relation
        self.mapper_maker = mapper_maker
        self.functional = functional

    def to_owl(self, owl_instance, obj, property_name, onto):
        mapper = self.mapper_maker()
        relation = resolve_property_name(self.relation, onto)

        if self.functional:
            target = mapper.to_owl(getattr(obj, property_name))
        else:
            target = [mapper.to_owl(e) for e in getattr(obj, property_name)]

        setattr(owl_instance, relation, target)

    def from_owl(self, owl_instance, onto):
        mapper = self.mapper_maker()
        relation = resolve_property_name(self.relation, onto)
        if self.functional:
            target = mapper.from_owl(getattr(owl_instance, relation))
        else:
            target = {mapper.from_owl(e) for e in getattr(owl_instance, relation)}
        return target

    def to_query(self, obj, property_name, onto):
        mapper = self.mapper_maker()
        if self.functional:
            target = mapper.to_owl(getattr(obj, property_name))
        else:
            target = [mapper.to_owl(e) for e in getattr(obj, property_name)]
        return resolve_property_name(self.relation, onto), target


class ListMapping(Mapping):
    def __init__(
        self,
        relation: str | NameWithNamespace,
        pivot_class: str | NameWithNamespace,
        connection_to_item: str | NameWithNamespace,
        item_mapper_maker: Callable[[], "Mapper"],
        index_property: str | NameWithNamespace = "sequence_number",
    ):

        self.relation = relation
        self.pivot_class = pivot_class
        self.connection_to_item = connection_to_item
        self.index_property = index_property

        self.item_mapper_maker = item_mapper_maker

    def to_owl(self, owl_instance, obj, property_name, onto):
        if onto is None:
            raise ValueError("onto parameter shouldn't be None for ListMapping")

        properties = {
            "relation": self.relation,
            "pivot_class": self.pivot_class,
            "connection_to_item": self.connection_to_item,
            "index_property": self.index_property,
        }
        for prop_name, value in properties.items():
            properties[prop_name] = resolve_property_name(value, onto)

        mapper = self.item_mapper_maker()
        elements = getattr(obj, property_name)
        pivots = [onto[properties["pivot_class"]]() for e in elements]

        for i, (element, pivot) in enumerate(zip(elements, pivots)):
            setattr(pivot, properties["connection_to_item"], mapper.to_owl(element))
            setattr(pivot, properties["index_property"], i)

        setattr(owl_instance, properties["relation"], pivots)

    def from_owl(self, owl_instance, onto):
        properties = {
            "relation": self.relation,
            "pivot_class": self.pivot_class,
            "connection_to_item": self.connection_to_item,
            "index_property": self.index_property,
        }
        for prop_name, value in properties.items():
            properties[prop_name] = resolve_property_name(value, onto)

        mapper = self.item_mapper_maker()
        pivots = sorted(
            getattr(owl_instance, properties["relation"]),
            key=lambda o: getattr(o, properties["index_property"]),
        )
        elements = [
            getattr(pivot, properties["connection_to_item"]) for pivot in pivots
        ]
        return [mapper.from_owl(e) for e in elements]


S = TypeVar("S")
T = TypeVar("T")


class Mapper[S, T]:

    def __init__(
        self,
        source_class: Type[S],
        target_class: Type[T] | NameWithNamespace,
        mappings: Dict[str, Mapping],
        ontology,
    ):
        self.source_class = source_class
        self.target_class = target_class
        self.mappings = mappings
        self.ontology = ontology

    def to_owl(self, obj: S) -> T:
        search_args = {}
        mappings = self.mappings

        # If there's a property flagged as primary key, use that one
        if primary_key := next(
            filter(lambda k: mappings[k].is_primary_key(), mappings), None
        ):
            mapping = mappings[primary_key]
            key, query = mapping.to_query(obj, primary_key, self.ontology)
            search_args[key] = query
        else:
            # Otherwise revert to searching for an entity matching all fields of the object
            for prop_name, mapping in self.mappings.items():
                try:
                    key, val = mapping.to_query(obj, prop_name, self.ontology)
                    search_args[key] = val
                except NotImplementedError:
                    warning(f"to_query method not implemented for {mapping.__class__}")

        try:
            classname, ns = self.target_class
            namespace = self.ontology.get_namespace(ns)
            target_class = namespace[classname]
        except TypeError:  # an actual owlready2 class was passed
            target_class = self.target_class

        search_result = self.ontology.search_one(type=target_class, **search_args)
        if search_result:
            owl_instance = search_result
        else:
            # otherwise create a new one
            owl_instance = target_class()
            for property_name, mapping in self.mappings.items():
                mapping.to_owl(owl_instance, obj, property_name, self.ontology)

        return owl_instance

    def from_owl(self, owl_instance: T) -> S:
        kwargs = {}

        for property_name, mapping in self.mappings.items():
            kwargs[property_name] = mapping.from_owl(owl_instance, self.ontology)

        return self.source_class(**kwargs)
