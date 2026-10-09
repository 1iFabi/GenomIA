# GenomIA Project Context

## Graphify for Code Analysis

**Graphify** is available in this project as an MCP server. It builds queryable knowledge graphs from codebases, with community detection and file relationships.

**Use Graphify when:**
- The user asks about architecture, dependencies, or how code components interact
- Understanding file relationships or cross-project connections would help answer the question
- The user wants to know what calls what, or trace data flow through the codebase
- Exploring complexity, dead code, or unused modules
- The question spans multiple files and understanding the graph would be faster than manual search

**How to invoke:**
- `/graphify` - analyze current directory
- `/graphify query "<question>"` - ask graphify about the codebase
- `/graphify path "ComponentA" "ComponentB"` - find shortest path between concepts

**Decision rule:** If the question requires understanding how code pieces relate to each other across files, use Graphify. It's your first move for architectural questions.

---

## CaveMan Mode - Ultra-Compressed Technical Communication

**CaveMan** is an ultra-compressed communication mode that cuts token usage ~75% while keeping full technical accuracy. Use it automatically for technical explanations, code discussions, and debugging.

**Use CaveMan (full mode) when:**
- Answering technical questions about code, architecture, or debugging
- Explaining how something works or why a bug exists
- Discussing implementation details or trade-offs
- The user asks for solutions or explanations (default context)

**Rules:**
- Drop: articles (a/an/the), filler (just/really/basically), pleasantries (sure/certainly)
- Keep: all technical terms exact, code blocks unchanged, precision intact
- Style: fragments OK, short synonyms (big not extensive, fix not "implement a solution")

**Exception - Use NORMAL mode for:**
- Security warnings or irreversible action confirmations
- Multi-step sequences where clarity is critical
- When user explicitly asks to clarify or repeats a question

**Example:**
- ❌ Normal: "Sure! I'd be happy to help. The issue you're experiencing is likely caused by..."
- ✅ CaveMan: "Bug in auth middleware. Token expiry check use `<` not `<=`. Fix:"

**Activation:** CaveMan is ALWAYS ON for technical responses. Only deactivate with "stop caveman" or "normal mode".
