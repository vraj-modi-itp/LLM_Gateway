keyword matching routing

 - pros: extremely fast execution time, zero compute cost, simple to implement and debug

 - cons: brittle against synonyms, cannot understand context or intent, requires constant manual updates

 - best use case: detecting explicit commands or highly structured queries where vocabulary is strictly defined

 - real life example: legacy customer support chatbots routing tickets based on words like refund or cancel

semantic vector routing

 - pros: understands meaning over exact wording, zero additional latency if caching already uses embeddings, highly accurate for nuanced intent

 - cons: requires managing a vector database, needs diverse examples to establish accurate centroids, less effective for single word commands

 - best use case: enterprise gateways balancing cost by routing casual chat to cheap models and complex tasks to expensive models

 - real life example: ai infrastructure proxies like portkey optimizing token routing

llm as a router

 - pros: zero training data required, handles extreme edge cases perfectly, easy to set up via simple prompting

 - cons: adds network latency from an extra api call, doubles the token cost per request, vulnerable to prompt injection

 - best use case: complex workflows where routing logic depends on deep reasoning rather than simple categorization

 - real life example: autonomous agents deciding which sub agent to invoke next based on conversation history

traditional machine learning classifiers

 - pros: sub millisecond latency, runs completely locally, highly accurate on domain specific data

 - cons: requires gathering thousands of labeled training examples, model must be retrained when user behavior changes, requires local compute resources

 - best use case: high throughput systems needing hyper fast classification without network overhead

 - real life example: automated email sorting systems separating invoices from marketing

metadata and explicit header routing

 - pros: deterministic and perfectly reliable, zero latency, enforces strict governance and access control

 - cons: forces the client application to decide the route, inflexible if user intent changes mid session, ignores payload content

 - best use case: multi tenant architectures where specific api keys or user tiers are restricted to specific models

 - real life example: cloudflare ai gateway routing traffic based on user subscription tiers like premium or free