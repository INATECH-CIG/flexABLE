import matplotlib.pyplot as plt
import random
import numpy as np

production = [1,1,1,1,0,1,1,1,1,1,1,0,0,0,0,0,0,1,1,0,0,0,0,0,1,1,0,1,1,1,1,0,0,0,0,0,0,0,0,0,0,1,1,1,1]
production_mit_flex = production.copy()
kosten = [0, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 7, 10, 6, 6, 1, 2, 0, 0, 5, 3, 8, 2, 6, 0, 0, 4, 0, 0, 0, 0, 5, 2, 5, 4, 3, 10, 3, 4, 5, 7, 0, 0, 0, 0]
T = len(production_mit_flex)

run_time = 2 # batch duration
downtime_min_long = 4 # minimum downtime if downtime > downtime_max_short
downtime_max_short = 1 # maximum downtime if downtime < downtime_min_long
max_power = 1 # maximum power of the machine


# determing possible sections in production timeline for prodviding flexibility (rumping up)
threshold = run_time + downtime_min_long  # min duration of a section to be considered for flexibility
zero_count = 0  # counter for determining the duration of a section (number of zeros in a row)
sections = True # List for saving start and end index of a section

# It is possible that there are different options for calling flexibility in one section. 
# In this case, the cheapest option is chosen. --> Solved in a while loop

while sections:
    sections = []

    # Determining section in production_mit_flex (this list needs to be chosen because it ensures going from section to section)
    for i, value in enumerate(production_mit_flex):
        if value == 0:
            zero_count += 1
            if zero_count == 1:
                current_section_start = i
        else:
            if zero_count >= threshold:
                current_section_end = i - 1
                sections.append((current_section_start, current_section_end))
            zero_count = 0
    print("Section: ", sections)

    # determining cheapest indexpair (current_section_start, current_section_end) in the section
    index_pairs = []  # list for saving all possible index pairs
    for start_index, end_index in sections:
        index_pairs_temp = []
        flexkosten_list = []

        #determine all possible index pairs in the section
        for i in range(start_index, end_index):
            steps_since_last_batch = i - start_index
            steps_to_next_batch = end_index - (i+1)
            if (steps_since_last_batch <= downtime_max_short or steps_since_last_batch >= downtime_min_long) and (steps_to_next_batch <= downtime_max_short or steps_to_next_batch >= downtime_min_long):
                index_pairs_temp.append((i,i+(run_time-1)))
                
 
            #determine the cheapest index pair in the section
            if i == end_index-1:
                print("index_pairs_temp: ", index_pairs_temp)
                for j in index_pairs_temp:
                    flexkosten = 0
                    for k in range(j[0], j[1]+1):
                        print("k: ", k)
                        flexkosten += kosten[k] * (max_power - production_mit_flex[k]) # costs for ramping to max power
                    flexkosten_list.append(flexkosten) 
                    print("flexkosten_list: ", flexkosten_list) 
                flex_block_index = flexkosten_list.index(min(flexkosten_list))
                index_1 = index_pairs_temp[flex_block_index][0]
                index_2 = index_pairs_temp[flex_block_index][1]
                production_mit_flex[index_1] = 1
                production_mit_flex[index_2] = 1

    # Prüfe den letzten Abschnitt am Ende
    if zero_count >= threshold:
        current_section_end = len(production_mit_flex) - 1
        sections.append((current_section_start, current_section_end))




            












# Erstelle eine Figur und die erste Achse (für die Produktion)
fig, ax1 = plt.subplots()

# Plot the production decision
ax1.step(range(0, T), production_mit_flex, where='post', label="Production mit flex (x)", color='blue')

# Plot production_ohne_flex
ax1.step(range(0, T), production, where='post', label="Production ohne Flex (y)", color='red')

ax1.set_xlim(0, T-1)  # Start- und Endintervall der x-Achse
ax1.set_xticks(np.arange(0, T, 5))  # Hier setzen Sie das Intervall von 5 für die Achsenbeschriftungen
ax1.set_ylabel("Production Value")
ax1.legend(loc='upper left')
ax1.grid(True)

plt.show()

# Erstelle eine separate Figur und Achse für die "Kosten"
fig2, ax2 = plt.subplots()

# Plot Kosten
ax2.step(range(0, T), kosten, where='post', label="Kosten", color='green')

ax2.set_xlim(0, T-1)  # Start- und Endintervall der x-Achse
ax2.set_xticks(np.arange(0, T, 5))  # Hier setzen Sie das Intervall von 5 für die Achsenbeschriftungen
ax2.set_ylabel("Kosten")
ax2.legend(loc='upper right')
ax2.grid(True)

plt.show()