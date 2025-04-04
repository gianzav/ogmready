import pytest
from typing import List, Set
from ogmready import *
from dataclasses import dataclass, field
import owlready2

from ogmready.ogmready import resolve_property_name


@dataclass
class Dog:
    name: str


@dataclass
class Car:
    model: str


@dataclass
class Person:
    name: str
    dog: Dog | None = None
    cars: List[Car] = field(default_factory=list)


@pytest.fixture
def onto():
    onto = owlready2.get_ontology("http://example.org/")
    other_namespace = "http://other.org/"

    with onto:

        class Person(owlready2.Thing):
            pass

        class Dog(owlready2.Thing):
            pass

        class Car(owlready2.Thing):
            pass

        class entity_name(owlready2.DataProperty, owlready2.FunctionalProperty):
            range = [str]

        class age(owlready2.DataProperty, owlready2.FunctionalProperty):
            range = [int]

        class id(owlready2.DataProperty, owlready2.FunctionalProperty):
            range = [int]

        class hasDog(owlready2.ObjectProperty, owlready2.FunctionalProperty):
            domain = [Person]
            range = [Dog]

        class List(owlready2.Thing):
            pass

        class ListItem(owlready2.Thing):
            pass

        class item(owlready2.ObjectProperty):
            domain = [List]
            range = [ListItem]

        class itemContent(owlready2.ObjectProperty, owlready2.FunctionalProperty):
            domain = [ListItem]
            range = [owlready2.Thing]

        class sequence_number(owlready2.DataProperty, owlready2.FunctionalProperty):
            range = [int]

    with onto.get_namespace(other_namespace):

        class color(owlready2.DataProperty):
            range = [str]

    return onto


class DogMapper(Mapper):
    __source_class__ = Dog
    __target_class__ = ("Dog", "http://example.org/")

    name = DataPropertyMapping("entity_name")


class CarMapper(Mapper):
    __source_class__ = Car
    __target_class__ = ("Car", "http://example.org/")

    model = DataPropertyMapping("entity_name")


class PersonMapper(Mapper):
    __source_class__ = Person
    __target_class__ = ("Person", "http://example.org/")

    name = DataPropertyMapping("entity_name")
    dog = ObjectPropertyMapping("hasDog", DogMapper)


def test_data_property_mapping_to_owl(onto):
    mapping = DataPropertyMapping("entity_name")
    dog = Dog("pluto")

    onto_dog = onto.Dog()

    mapping.to_owl(onto_dog, dog, "name", onto)

    assert onto_dog.entity_name == dog.name


def test_data_property_mapping_from_owl(onto):
    mapping = DataPropertyMapping("entity_name")
    onto_dog = onto.Dog()
    onto_dog.entity_name = "pluto"

    assert mapping.from_owl(onto_dog, onto) == "pluto"


def test_object_property_mapping_to_owl(onto):
    d = Dog("pluto")
    p = Person("mario", d)

    mapping = ObjectPropertyMapping("hasDog", DogMapper)

    onto_person = onto.Person()
    mapping.to_owl(onto_person, p, "dog", onto)

    assert onto_person.hasDog.entity_name == d.name


def test_object_property_mapping_from_owl(onto):
    d = Dog("pluto")
    p = Person("mario", d)

    mapping = ObjectPropertyMapping("hasDog", DogMapper)

    onto_person = onto.Person()
    onto_dog = onto.Dog()
    onto_dog.entity_name = "pluto"
    onto_person.hasDog = onto_dog
    assert mapping.from_owl(onto_person, onto) == d


def test_list_mapping_to_owl(onto):
    cars = [Car("model1"), Car("model2")]
    p = Person("luigi", cars=cars)

    mapping = ListMapping(
        "item",
        ("ListItem", "http://example.org/"),
        "itemContent",
        CarMapper,
        "sequence_number",
        default_factory=list,
    )

    onto_person = onto.Person()

    mapping.to_owl(onto_person, p, "cars", onto)
    assert all(
        x.itemContent.entity_name == car.model for x, car in zip(onto_person.item, cars)
    )


def test_list_mapping_from_owl(onto):
    cars = [Car("model1"), Car("model2")]
    p = Person("luigi", cars=cars)

    mapping = ListMapping(
        "item",
        ("ListItem", "http://example.org/"),
        "itemContent",
        CarMapper,
        "sequence_number",
        default_factory=list,
    )

    onto_person = onto.Person()
    onto_cars = [onto.Car() for car in cars]
    for i, (onto_car, car) in enumerate(zip(onto_cars, cars)):
        onto_car.entity_name = car.model
        item = onto.ListItem()
        item.sequence_number = i
        item.itemContent = onto_car
        onto_person.item.append(item)

    assert cars == mapping.from_owl(onto_person, onto)


def test_lazy_result_force(onto):
    class PersonMapper(Mapper):
        __source_class__ = Person
        __target_class__ = ("Person", "http://example.org/")

        name = DataPropertyMapping("entity_name")
        dog = ObjectPropertyMapping("hasDog", DogMapper)
        cars = ListMapping(
            "item",
            ("ListItem", "http://example.org/"),
            "itemContent",
            CarMapper,
            "sequence_number",
            default_factory=list,
        )

    d = Dog("pippo")
    car = Car("ferrari")
    p = Person("mario", d, [car])

    person_mapper = PersonMapper(onto)
    onto_person = person_mapper.to_owl(p)
    person_lazy = person_mapper.from_owl(onto_person, lazy=True)

    assert person_lazy._force() == p


def test_lazy_from_owl(onto):
    class PersonMapper(Mapper):
        __source_class__ = Person
        __target_class__ = ("Person", "http://example.org/")

        name = DataPropertyMapping("entity_name")
        dog = ObjectPropertyMapping("hasDog", DogMapper)
        cars = ListMapping(
            "item",
            ("ListItem", "http://example.org/"),
            "itemContent",
            CarMapper,
            "sequence_number",
            default_factory=list,
        )

    d = Dog("pippo")
    car = Car("ferrari")
    p = Person("mario", d, [car])

    person_mapper = PersonMapper(onto)
    onto_person = person_mapper.to_owl(p)
    person_lazy = person_mapper.from_owl(onto_person, lazy=True)

    assert person_lazy == p


def test_resolve_property_name(onto):
    prop_name = resolve_property_name(("entity_name", "http://example.org/"), onto)
    assert prop_name == "ogmready__http_example_org_entity_name"


def test_access_property_with_generated_property_name(onto):
    p = onto.Person()
    p.entity_name = "pippo"  # before property renaming, accessed with entity_name
    prop_name = resolve_property_name(("entity_name", "http://example.org/"), onto)

    assert getattr(p, prop_name) == "pippo"
