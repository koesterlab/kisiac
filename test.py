class Singleton:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._instance = None         # each subclass gets its own instance
        cls._initialized = False     # and its own init flag

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, *args, **kwargs):
        if self._initialized:
            return  # skip repeated initialization
        # one-time initialization logic goes here
        super().__init__(*args, **kwargs)
        self._initialized = True

class A(Singleton):
    def __init__(self):
        print("A init")

class B(Singleton):
    def __init__(self):
        print("B init")


a1 = A()
a2 = A()
b1 = B()
b2 = B()