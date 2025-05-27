from logging import warning
from typing import Any, Callable, Literal, Tuple, TypeVar, override
import owlready2
import inflection


type NameWithNamespace = Tuple[str, str]

type Operator = Literal["=", "!=", "IN", "CONTAINS"]


def resolve_property_name(
    name: str | NameWithNamespace, onto: owlready2.Ontology, iri=False
) -> str:
    if isinstance(name, str):
        if iri:
            result = onto[name].iri
        else:
            result = name
    else:
        try:
            prop, ns = name
            namespace: owlready2.Namespace = onto.get_namespace(ns)
            if iri:
                result = namespace[prop].iri
            else:
                ns_prop = namespace[prop]
                # use a special python name for the property
                # the ontology needs to include the python_name annotation in this format
                result = "ogmready__" + inflection.underscore(
                    inflection.parameterize(ns_prop.iri)
                )
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

    def from_owl(self, owl_instance, onto: owlready2.Ontology, lazy=False):
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
        default_factory: None | Callable = None,
    ):
        self.target_property = target_property
        self.functional = functional
        self.primary_key = primary_key
        self.default_factory = default_factory

    def to_owl(self, owl_instance, obj, property_name, onto, update=False):
        # update doesn't make a difference for data properties

        target_property = resolve_property_name(self.target_property, onto)
        if self.functional:
            target = getattr(obj, property_name)
        else:
            target = [e for e in getattr(obj, property_name)]

        setattr(owl_instance, target_property, target)

    def from_owl(self, owl_instance, onto, lazy=False):
        target_property = resolve_property_name(self.target_property, onto)

        if hasattr(owl_instance, target_property):
            if self.functional:
                target = getattr(owl_instance, target_property)
            else:
                target = set(getattr(owl_instance, target_property))
        elif self.default_factory:
            target = self.default_factory()
        else:
            raise AttributeError(
                f"{target_property} not present for {owl_instance.name}, and no default has been provided."
            )

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
        mapper_maker: Callable[[owlready2.Ontology], "Mapper"],
        functional=True,
        default_factory: None | Callable = None,
    ):
        self.relation = relation
        self.mapper_maker = mapper_maker
        self.functional = functional
        self.default_factory = default_factory

    def to_owl(self, owl_instance, obj, property_name, onto, update=False):
        # update doesn't make a difference
        mapper = self.mapper_maker(onto)
        relation = resolve_property_name(self.relation, onto)

        if self.functional:
            target = mapper.to_owl(getattr(obj, property_name, update))
        else:
            target = [mapper.to_owl(e, update) for e in getattr(obj, property_name)]

        setattr(owl_instance, relation, target)

    def from_owl(self, owl_instance, onto, lazy=False):
        mapper = self.mapper_maker(onto)
        relation = resolve_property_name(self.relation, onto)

        if hasattr(owl_instance, relation):
            if self.functional:
                target = mapper.from_owl(getattr(owl_instance, relation), lazy=lazy)
            else:
                target = {
                    mapper.from_owl(e, lazy=lazy)
                    for e in getattr(owl_instance, relation)
                }
        elif self.default_factory:
            target = self.default_factory()
        else:
            raise AttributeError(
                f"{relation} not present for {owl_instance.name}, and no default has been provided."
            )

        return target

    def to_query(self, obj, property_name, onto):
        mapper = self.mapper_maker(onto)
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
        item_mapper_maker: Callable[[owlready2.Ontology], "Mapper"],
        index_property: str | NameWithNamespace = "sequence_number",
        default_factory: None | Callable = None,
    ):

        self.relation = relation
        self.pivot_class = pivot_class
        self.connection_to_item = connection_to_item
        self.index_property = index_property
        self.item_mapper_maker = item_mapper_maker
        self.default_factory = default_factory

    def _resolve_properties(self, onto, iri=False):
        properties = {
            "relation": self.relation,
            "pivot_class": self.pivot_class,
            "connection_to_item": self.connection_to_item,
            "index_property": self.index_property,
        }
        for prop_name, value in properties.items():
            if prop_name != "pivot_class":
                properties[prop_name] = resolve_property_name(value, onto, iri)
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
        mapper = self.item_mapper_maker(onto)
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

    def from_owl(self, owl_instance, onto, lazy=False):
        properties = self._resolve_properties(onto)
        mapper = self.item_mapper_maker(onto)

        if hasattr(owl_instance, properties["relation"]):
            pivots = sorted(
                getattr(owl_instance, properties["relation"]),
                key=lambda o: getattr(o, properties["index_property"]),
            )
            elements = [
                getattr(pivot, properties["connection_to_item"]) for pivot in pivots
            ]
            return [mapper.from_owl(e, lazy=lazy) for e in elements]
        elif self.default_factory:
            return self.default_factory()
        else:
            raise AttributeError(
                f"{properties['relation']} not present for {owl_instance.name}, and no default has been provided."
            )

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


def make_lazy(owl_instance, mapper, ontology):
    class LazyResult(mapper.source_class):
        """
        Proxy object for lazily loading attributes from an OWL individual while
        simulating the domain class `S`.
        """

        def __init__(self, owl_instance, mapper, ontology):
            self._owl_instance = owl_instance
            self._mapper = mapper
            self._ontology = ontology
            self._resolved_fields = {}
            self._simulated_class = mapper.source_class  # The simulated class

        @override
        def __getattr__(self, name):
            """
            Lazily resolve the field when it is accessed.
            """
            # If the field has already been resolved, return it
            if name in self._resolved_fields:
                return self._resolved_fields[name]

            # If the field is not in the mapper's mappings, raise an AttributeError
            if name not in self._mapper.mappings:
                raise AttributeError(
                    f"'{self._simulated_class.__name__}' object has no attribute '{name}'"
                )

            # Resolve the field using the appropriate mapping
            mapping = self._mapper.mappings[name]
            resolved_value = mapping.from_owl(
                self._owl_instance, self._ontology, lazy=True
            )

            # Cache the resolved value and return it
            self._resolved_fields[name] = resolved_value
            return resolved_value

        def _force(self):
            for name in self._mapper.mappings:
                if name not in self._resolved_fields:
                    mapping = self._mapper.mappings[name]
                    resolved_value = mapping.from_owl(
                        self._owl_instance, self._ontology, lazy=False
                    )
                    self._resolved_fields[name] = resolved_value
            return self._simulated_class(**self._resolved_fields)

        def __class__(self):
            """
            Simulate the class of the domain object.
            """
            return self._simulated_class

        def __dir__(self):
            """
            Simulate the attributes of the domain object for introspection.
            """
            return list(self._mapper.mappings.keys())

        def __repr__(self):
            """
            Simulate a meaningful representation of the object.
            """
            return f"<Lazy {self._simulated_class.__name__} proxy for {self._owl_instance}>"

        def __setattr__(self, name, value):
            """
            Allow setting attributes dynamically, with special handling for proxy internals.
            """
            # Protect internal attributes
            if name.startswith("_"):
                super().__setattr__(name, value)
            elif name in self._mapper.mappings:
                # If the attribute is part of the mapped fields, resolve it lazily
                self._resolved_fields[name] = value
            else:
                raise AttributeError(
                    f"Cannot dynamically set unmapped attribute '{name}'"
                )

        def __eq__(self, other):
            """
            Equality comparison, based on the underlying OWL individual.
            """
            if isinstance(other, self._simulated_class):
                return self._force() == other

            return False

        def __hash__(self):
            return hash(self._owl_instance)

    return LazyResult(owl_instance, mapper, ontology)


class Mapper[S, T]:
    __source_class__: S
    __target_class__: T

    def __init__(
        self,
        ontology,
    ):
        self.source_class = self.__class__.__source_class__
        if isinstance(self.__class__.__target_class__, tuple):
            self.target_class = resolve_class(self.__class__.__target_class__, ontology)

        self.mappings = {
            name: mapping
            for name, mapping in self.__class__.__dict__.items()
            if isinstance(mapping, Mapping)
        }

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

    def from_owl(self, owl_instance: T, lazy=False) -> S:
        if owl_instance is None:
            return None

        if lazy:
            return make_lazy(owl_instance, self, self.ontology)

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
            search_args = self.to_query(obj)
            search_result = self.ontology.search_one(
                type=self.target_class, **search_args
            )
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
