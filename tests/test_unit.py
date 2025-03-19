import pytest
from typing import List, Set
from ogmready.ogmready import *
from dataclasses import dataclass, field
import owlready2


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
    def __init__(self, ontology):
        mappings = {
            "name": DataPropertyMapping("entity_name"),
        }
        super().__init__(Dog, ("Dog", "http://example.org/"), mappings, ontology)


class CarMapper(Mapper):
    def __init__(self, ontology):
        mappings = {
            "model": DataPropertyMapping("entity_name"),
        }
        super().__init__(Car, ("Car", "http://example.org/"), mappings, ontology)


class PersonMapper(Mapper):
    def __init__(self, ontology):
        mappings = {
            "name": DataPropertyMapping("entity_name"),
            "dog": ObjectPropertyMapping("hasDog", lambda: DogMapper(ontology)),
        }
        super().__init__(Person, "Person", mappings, ontology)


# d = Dog(1, "pluto", {"black", "white"})
# p = Person(2, "mario", 10, d)

# person_mapper = PersonMapper(onto)
# dog_mapper = DogMapper(onto)


# onto_dog = dog_mapper.to_owl(d)
# onto_person = person_mapper.to_owl(p)


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

    class DogMapper(Mapper):
        def __init__(self, ontology):
            mappings = {
                "name": DataPropertyMapping("entity_name"),
            }
            super().__init__(Dog, ("Dog", "http://example.org/"), mappings, ontology)

    mapping = ObjectPropertyMapping("hasDog", lambda: DogMapper(onto))

    onto_person = onto.Person()
    mapping.to_owl(onto_person, p, "dog", onto)

    assert onto_person.hasDog.entity_name == d.name


def test_object_property_mapping_from_owl(onto):
    d = Dog("pluto")
    p = Person("mario", d)

    mapping = ObjectPropertyMapping("hasDog", lambda: DogMapper(onto))

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
        lambda: CarMapper(onto),
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
        lambda: CarMapper(onto),
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
