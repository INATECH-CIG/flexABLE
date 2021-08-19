# flexABLE
flexABLE stands for “**Flex**ibility-oriented **A**gent-**B**ased **L**aboratory for **E**lectricity system analysis”. flexABLE is an open-source Python-based toolbox to simulate European electricity markets focusing on the German bidding zone. The toolbox could be used to backcast electricity prices of previous years and the unit-wise power generations.

Documentation
-------------
The authors are currently working on writing a documentation for the model. A paper describing the mathematical model is currently in revision process.

Installation
------------
Currently the model is not prepared as an installable package, but the example.py file give a glimpse of how the model could be setup.
We will try to update this section as fast as possible, but meanwhile please do nt hesitate to write us an email (ramiz.qussous@inatech.uni-freiburg.de) and we could help you setup the model and required packages. 


Release Status
------------
flexABLE is a part of ongoing PhD theses, This means it will keep changing to include new functionality or to improve existing features. The current example provided are backcasting scenarios for the years 2016-2019 and more scenarios will be provided soon. Currently Nick and I (Ramiz) are working on developing the model to include features such as electric networks, neural network agents. The methodology used focuses more on rebuilding the energy side of the model as best as possible, bus since we are not software engineers, the "program" is not written with robustness in mind and our experience is limited when it comes to common best practices. Expect errors, bug, funky behavior and code structures. (Special thanks to developers of POMATO model for the nice formulation, which I used as inspiration for this section).