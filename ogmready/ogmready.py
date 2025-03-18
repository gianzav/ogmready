from logging import warning
from typing import Any, Callable, Dict, Iterable, Tuple, Type, TypeVar
import owlready2

type NameWithNamespace = Tuple[str, str]


def resolve_property_name(
    name: str | NameWithNamespace, onto: owlready2.Ontology
) -> str:
    if isinstance(name, str):
        result = name
    else:
        try:
            prop, ns = name
            namespace: owlready2.Namespace = onto.get_namespace(ns)
            result = namespace[prop].name
        except AttributeError as e:
            print(f"Property {prop} not found in namespace {ns}")
            raise e

    return result


def resolve_class(
    name: NameWithNamespace, onto: owlready2.Ontology
) -> owlready2.ThingClass:
    try:
        prop, ns = name
        namespace: owlready2.Namespace = onto.get_namespace(ns)
        result = namespace[prop]
        return result
    except AttributeError as e:
        print(f"Property {prop} not found in namespace {ns}")
        raise e


class Mapping:
    def to_owl(
        self, owl_instance, obj, property_name, onto: owlready2.Ontology, update=False
    ):
        raise NotImplementedError

    def from_owl(self, owl_instance, onto: owlready2.Ontology):
        raise NotImplementedError

    def to_query(self, obj, property_name, onto) -> Tuple[str, Any]:
        raise NotImplementedError

    def is_primary_key(self):
        return False

    def delete(self, owl_instance, property_name, onto: owlready2.Ontology):
        """
        Deletes the data associated with this mapping from the ontology.
        """
        raise NotImplementedError


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

    def to_owl(self, owl_instance, obj, property_name, onto, update=False):
        # update doesn't make a difference for data properties

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

    def delete(self, owl_instance, property_name, onto: owlready2.Ontology):
        # Resolve the target property
        target_property = resolve_property_name(self.target_property, onto)

        # Remove the property value from the OWL individual
        if hasattr(owl_instance, target_property):
            delattr(owl_instance, target_property)


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

    def to_owl(self, owl_instance, obj, property_name, onto, update=False):
        # update doesn't make a difference
        mapper = self.mapper_maker()
        relation = resolve_property_name(self.relation, onto)

        if self.functional:
            target = mapper.to_owl(getattr(obj, property_name, update))
        else:
            target = [mapper.to_owl(e, update) for e in getattr(obj, property_name)]

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

    def delete(self, owl_instance, property_name, onto: owlready2.Ontology):
        # Resolve the relation (object property)
        relation = resolve_property_name(self.relation, onto)

        # Remove the object property value
        if hasattr(owl_instance, relation):
            delattr(owl_instance, relation)


class ListMapping(Mapping):
    def __init__(
        self,
        relation: str | NameWithNamespace,
        pivot_class: NameWithNamespace,
        connection_to_item: str | NameWithNamespace,
        item_mapper_maker: Callable[[], "Mapper"],
        index_property: str | NameWithNamespace = "sequence_number",
    ):

        self.relation = relation
        self.pivot_class = pivot_class
        self.connection_to_item = connection_to_item
        self.index_property = index_property

        self.item_mapper_maker = item_mapper_maker

    def _resolve_properties(self, onto):
        properties = {
            "relation": self.relation,
            "pivot_class": self.pivot_class,
            "connection_to_item": self.connection_to_item,
            "index_property": self.index_property,
        }
        for prop_name, value in properties.items():
            if prop_name != "pivot_class":
                properties[prop_name] = resolve_property_name(value, onto)
            else:
                properties["pivot_class"] = resolve_class(value, onto)

        assert properties["relation"] is not None
        assert properties["pivot_class"] is not None
        assert properties["connection_to_item"] is not None
        assert properties["index_property"] is not None

        return properties

    def to_owl(self, owl_instance, obj, property_name, onto, update=False):
        if onto is None:
            raise ValueError("onto parameter shouldn't be None for ListMapping")

        properties = self._resolve_properties(onto)
        mapper = self.item_mapper_maker()
        elements = getattr(obj, property_name)

        if update:
            # delete the previous pivots
            for pivot in getattr(owl_instance, properties["relation"]):
                owlready2.destroy_entity(pivot)

        pivots = [properties["pivot_class"]() for e in elements]

        for i, (element, pivot) in enumerate(zip(elements, pivots)):
            setattr(
                pivot, properties["connection_to_item"], mapper.to_owl(element, update)
            )
            setattr(pivot, properties["index_property"], i)

        setattr(owl_instance, properties["relation"], pivots)

    def from_owl(self, owl_instance, onto):
        properties = self._resolve_properties(onto)
        mapper = self.item_mapper_maker()
        pivots = sorted(
            getattr(owl_instance, properties["relation"]),
            key=lambda o: getattr(o, properties["index_property"]),
        )
        elements = [
            getattr(pivot, properties["connection_to_item"]) for pivot in pivots
        ]
        return [mapper.from_owl(e) for e in elements]

    def delete(self, owl_instance, property_name, onto: owlready2.Ontology):
        # Resolve properties and classes
        properties = self._resolve_properties(onto)
        # Retrieve existing pivots
        pivots = getattr(owl_instance, properties["relation"], [])

        # Destroy all pivot elements
        for pivot in pivots:
            owlready2.destroy_entity(pivot)

        # Remove the relation from the OWL individual
        if hasattr(owl_instance, properties["relation"]):
            delattr(owl_instance, properties["relation"])


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
        if isinstance(target_class, tuple):
            self.target_class = resolve_class(target_class, ontology)
        else:
            self.target_class = target_class
        self.mappings = mappings
        self.ontology = ontology

    def to_owl(self, obj: S, update=False) -> T:
        if obj is None:
            return None

        # search if the wanted instance is already present
        search_args = self.to_query(obj)
        search_result = self.ontology.search_one(type=self.target_class, **search_args)
        if search_result:
            owl_instance = search_result
            if update:
                for property_name, mapping in self.mappings.items():
                    mapping.to_owl(
                        owl_instance, obj, property_name, self.ontology, update
                    )
        else:
            # otherwise create a new one
            owl_instance = self.target_class()

        # apply the mappings only if a new instance has been created or it has to be updated
        if update or (not search_result):
            for property_name, mapping in self.mappings.items():
                mapping.to_owl(owl_instance, obj, property_name, self.ontology, update)

        return owl_instance

    def from_owl(self, owl_instance: T) -> S:
        if owl_instance is None:
            return None

        kwargs = {}

        for property_name, mapping in self.mappings.items():
            kwargs[property_name] = mapping.from_owl(owl_instance, self.ontology)

        return self.source_class(**kwargs)

    def to_query(self, obj):
        mappings = self.mappings
        search_args = {}
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
        return search_args

    def delete_mapping(self, obj: S | T):
        if obj is None:
            return

        if isinstance(obj, self.source_class):
            # search if the wanted instance is already present
            target_class, search_args = self.to_query(obj)
            search_result = self.ontology.search_one(type=target_class, **search_args)
            if search_result:
                owl_instance = search_result
        elif isinstance(obj, self.target_class):
            owl_instance = obj
        else:
            raise ValueError(
                "The object passed is neither of source nor target class for mapping."
            )

        for property_name, mapping in self.mappings.items():
            mapping.delete(owl_instance, property_name, self.ontology)
        owlready2.destroy_entity(owl_instance)
