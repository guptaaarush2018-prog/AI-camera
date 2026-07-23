Claude Presentation Prompt
You are an expert presentation designer, systems engineer, and technical storyteller. Your goal is to create a presentation that looks like it was produced by a professional engineering team for a university capstone defense, research symposium, or technology competition.
I have attached my complete system architecture/design document. Use it as the primary source of truth. Do not simply summarize the document. Instead, synthesize the information into a compelling presentation that demonstrates both the engineering problem and the technical solution.
Objective
Create a 10–11 slide presentation that clearly answers:
What is the problem?
Why does it matter?
How does computer vision understand traffic?
Why is the proposed architecture effective?
Why is it safe?
What impact could it have?
The presentation should tell a logical story from problem → analysis → solution → implementation → impact.
Design Requirements
Create a presentation with the quality of a TED Talk, Apple keynote, NVIDIA GTC presentation, or MIT engineering capstone.
Style:
Modern engineering aesthetic
White background
Blue and teal accents
Clean sans-serif typography
Large diagrams
Minimal text
Professional icons
Plenty of whitespace
Consistent spacing and alignment
Avoid clutter.
Every slide should communicate one central idea.
Prefer diagrams over paragraphs.
Critical Instructions
Do not copy sections of my document verbatim.
Instead:
Rewrite content for presentation format.
Condense information into visuals.
Replace paragraphs with diagrams, flowcharts, comparison tables, timelines, and infographics.
Use concise speaker-friendly text.
The audience should understand the presentation without reading long paragraphs.
Statistics
The statistics below are supporting evidence.
Only use a statistic when it directly reinforces the message of that slide.
Do not force every statistic into the presentation.
If a statistic does not strengthen the point, omit it.
Whenever a statistic is used:
Pair it with an appropriate chart, infographic, icon, or comparison.
Integrate it naturally into the slide narrative.
Never place statistics in isolation.
Presentation Structure
Slide 1 — Title
Project title
Subtitle
Author
Hero image of a modern smart intersection.

Safety Layer
↓
Traffic Controller
This should be the centerpiece of the presentation.
Slide 5 — Edge AI & Distributed Coordination
Explain why inference occurs on-device rather than in the cloud.
Compare:
Latency
Bandwidth
Privacy
Reliability
Cost
Illustrate how intersections exchange only lightweight MQTT messages.
Slide 6 — Safety & Reliability
Explain why AI never directly controls traffic lights.
Show:
AI Recommendation
↓
Safety Layer
Emergency vehicle prioritization
Pedestrian-aware crossings
Continuous validation
Real-world deployment
Slide 8 — Demonstration & Validation
Explain:
Real Raspberry Pi + Hailo hardware
Simulated neighboring intersections
MQTT communication
SUMO simulation
Live object detection
Include a demonstration architecture diagram.
Slide 9 — Expected Impact
Present only statistics that demonstrate the effectiveness of intelligent traffic control.
Examples include:
40% lower wait times, 25% shorter travel times, 21% lower emissions (Surtrac)
40% lower intersection delays and 900 hours of delay eliminated (NoTraffic)
10–20% lower delays and fuel use (Google Project Green Light)
20% faster buses and 10% faster cyclists (Copenhagen)
30–45 seconds saved for emergency vehicles (Fairfax County)
Clearly state these are results from existing smart traffic systems that validate the overall approach—not results achieved by this project.
Present the information using comparison charts rather than bullet points.
Slide 10 — Conclusion
Summarize:
The problem
The proposed solution
Key innovations
Future deployment
End with a concise statement emphasizing safer, smarter, and more efficient intersections.
Speaker Notes
For every slide, generate concise speaker notes that expand on the visuals without reading the slide verbatim.
Final Quality Expectations
This presentation should not resemble a typical student PowerPoint. It should feel like a polished engineering conference presentation or startup pitch deck. Prioritize visual communication, logical flow, and technical accuracy. Every slide should have a single clear message, professionally designed layouts, and graphics that reinforce the content. Use the attached document as the authoritative reference, but improve its presentation for a technical audience rather than reproducing it.

