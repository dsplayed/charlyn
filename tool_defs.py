"""Tool definitions for native Ollama function calling."""
from typing import List, Dict, Any

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using Serper (Google search API). Returns organic results with titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "gl": {"type": "string", "description": "Google search region (country code, e.g. th for Thailand, us for United States)", "default": "th"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 8)", "default": 8}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_scrape",
            "description": "Scrape the content of a web page using Serper. Returns the page title, description, and text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to scrape"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 15)", "default": 15}
                },
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_deep_search",
            "description": "Deep search: searches the web AND scrapes the top results for full page content. Use this when you need detailed info beyond snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "gl": {"type": "string", "description": "Search region (country code, e.g. th, us)", "default": "th"},
                    "max_scrape": {"type": "integer", "description": "Number of top results to scrape (default 3)", "default": 3},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 15)", "default": 15}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "username_search",
            "description": "Search a username across multiple platforms (GitHub, Twitter, Reddit, Instagram, YouTube, TikTok, Twitch, SoundCloud, Online Sequencer, portfolio sites, etc.). Returns found profiles and links.",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "The username or alias to search for"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 15)", "default": 15}
                },
                "required": ["username"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "dns_lookup",
            "description": "Look up DNS records for a domain. Supports A, AAAA, MX, TXT, NS, CNAME, SOA record types.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "The domain to look up (e.g. example.com)"},
                    "record_type": {"type": "string", "description": "DNS record type: A, AAAA, MX, TXT, NS, CNAME, SOA", "default": "A"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 8)", "default": 8}
                },
                "required": ["domain"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "whois_lookup",
            "description": "Perform a WHOIS lookup on a domain to get registration details, registrar, dates, name servers, and contacts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "The domain to look up (e.g. example.com)"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 15)", "default": 15}
                },
                "required": ["domain"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ip_info",
            "description": "Get geolocation, ISP, ASN, and proxy/VPN info for an IP address using ip-api.com.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ip": {"type": "string", "description": "The IP address to look up"}
                },
                "required": ["ip"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wayback_urls",
            "description": "Find historical snapshots of a domain from the Wayback Machine. Returns timestamps and original URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "The domain to search (e.g. example.com)"},
                    "limit": {"type": "integer", "description": "Max results to return (default 20)", "default": 20},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 15)", "default": 15}
                },
                "required": ["domain"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate the browser to a specific URL and return the page title, URL, and visible text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to navigate to"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click an element on the current page by CSS selector or visible text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector or visible text of the element to click"}
                },
                "required": ["selector"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "Type text into an input field on the current page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of the input field"},
                    "text": {"type": "string", "description": "Text to type"}
                },
                "required": ["selector", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Take a screenshot of the current browser page. Returns the file path to the saved PNG image.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "vm_screenshot",
            "description": "Take a screenshot of the virtual machine (Debian VM running via QEMU). Saves to the screenshots directory and returns the file path. Useful for seeing what's on the VM screen.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "vm_mouse_move",
            "description": "Move the VM mouse cursor to absolute pixel coordinates (x, y). Screen is 1280x800.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate (0-1279)"},
                    "y": {"type": "integer", "description": "Y coordinate (0-799)"}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "vm_click",
            "description": "Click at pixel coordinates (x, y) on the VM. Left button by default, or use button=3 for right-click.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                    "button": {"type": "integer", "description": "Mouse button: 1=left, 2=middle, 3=right (default 1)", "default": 1}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "vm_type",
            "description": "Type text into the currently focused field on the VM. Sends keyboard input via VNC.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "vm_key",
            "description": "Press a special key on the VM. Common keys: enter, tab, escape, backspace, delete, up, down, left, right, home, end, pageup, pagedown, super (Windows key), ctrl-c, ctrl-v, ctrl-a, shift-tab, alt-f4, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key name to press"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "vm_find_text",
            "description": "Scan the VM screen for specific text and return its coordinates. Also returns a rough layout of all visible text on screen. Useful for finding buttons, labels, and UI elements before clicking them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to search for on the VM screen"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "vm_terminal",
            "description": "Run a shell command inside the VM via SSH. Use this to install software, edit configs, run scripts, or do anything on the VM that requires a terminal. Returns command output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to run inside the VM"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)", "default": 30}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "vm_click_text",
            "description": "Find text on the VM screen and click at its center. Uses OCR to locate the text position. Best for clicking buttons, links, and labeled UI elements.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Exact text to find and click"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ocr_analyze",
            "description": "Run OCR (text recognition) on an image file. Returns all visible text extracted from the image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {"type": "string", "description": "Absolute path to the image file"}
                },
                "required": ["image_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "terminal",
            "description": "Run a terminal/shell command on the local system. Dangerous commands warn unless --yolo is enabled. If Docker is available, commands run inside a sandboxed container.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "python_execute",
            "description": "Execute Python code in an isolated subprocess. Returns stdout, stderr, and exit code. Great for data analysis, calculations, text processing, and code generation tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The Python code to execute"},
                    "timeout": {"type": "integer", "description": "Max execution time in seconds (default 30)", "default": 30}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_store",
            "description": "Save an important fact, preference, or piece of information to persistent memory. The AI chooses what is worth remembering across sessions. Use this for user preferences, key facts discovered, important context, or any information that should be recalled later.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The fact or information to remember"},
                    "category": {"type": "string", "description": "Category for organization (e.g. preference, fact, context, discovery, user_info)", "default": "general"}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_recall",
            "description": "Retrieve saved memories. Use this when you need to remember something you previously stored, or to recall user preferences and past discoveries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of recent memories to retrieve (default 15)", "default": 15}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read the contents of a file. Returns the full text content (truncated if very large).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative or absolute path to the file"},
                    "limit": {"type": "integer", "description": "Max lines to read (default 2000)", "default": 2000}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "Write text to a file. Creates the file if it doesn't exist, overwrites if it does. Use append=False to overwrite (default), append=True to append.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative or absolute path to the file"},
                    "content": {"type": "string", "description": "Text content to write"},
                    "append": {"type": "boolean", "description": "If true, append instead of overwrite", "default": False}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_delete",
            "description": "Delete a file. Returns success or error message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative or absolute path to the file"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_exists",
            "description": "Check if a file or directory exists. Returns true/false and type (file or directory).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative or absolute path"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "file_search",
            "description": "Search for text inside files in a directory. Uses grep-like matching. Returns matching files and lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text or regex pattern to search for"},
                    "path": {"type": "string", "description": "Directory to search in (default .)", "default": "."},
                    "include": {"type": "string", "description": "File glob pattern to include, e.g. '*.py' or '*.md'", "default": "*"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "dir_list",
            "description": "List files and directories inside a given path. Returns a structured list with names, sizes, and types.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to list (default .)", "default": "."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "dir_create",
            "description": "Create a new directory (and parent directories if needed). Returns success or error.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative or absolute path of the directory to create"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "dir_delete",
            "description": "Delete a directory and all its contents recursively. Be careful — this is destructive.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative or absolute path of the directory to delete"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "plan",
            "description": "Create a step-by-step plan before starting a complex task. Use this to think through what needs to be done before executing tools. The plan will be shown to you as context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The task to create a plan for"}
                },
                "required": ["task"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_students",
            "description": "Search for students by name or student ID. Returns matching student records with basic info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Name or student ID to search for"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_student",
            "description": "Get detailed information for a single student by their student ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "string", "description": "The numeric student ID (e.g. 17388)"}
                },
                "required": ["student_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_students_by_class",
            "description": "Get all students enrolled in a specific classroom. Class format examples: ม. 1/3 ESC, ม. 6/2 วิท, ม. 3/1 ESL",
            "parameters": {
                "type": "object",
                "properties": {
                    "class": {"type": "string", "description": "Classroom identifier (e.g. ม. 1/3 ESC)"}
                },
                "required": ["class"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_classes",
            "description": "List all available classrooms with student counts.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gfn",
            "description": "Check NVIDIA GeForce NOW server queue positions across all regions. Returns current queue length and estimated wait time per server. Optionally filter by region.",
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Filter by region code: US, EU, CA, IN, JP, KR, THAI, MY. Leave empty for all regions.", "default": ""},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 8)", "default": 8}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "anime_search",
            "description": "Search for anime on MyAnimeList by title. Returns matching anime with scores, episodes, status, and synopses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The anime title to search for (e.g. Naruto, Attack on Titan)"},
                    "limit": {"type": "integer", "description": "Max results (default 5, max 25)", "default": 5},
                    "type": {"type": "string", "description": "Filter by type: tv, movie, ova, special, ona, music", "default": ""},
                    "min_score": {"type": "number", "description": "Minimum score filter (1-10)", "default": 0},
                    "status": {"type": "string", "description": "Filter by status: airing, complete, upcoming", "default": ""},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 8)", "default": 8}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "anime_get",
            "description": "Get detailed information about a specific anime by its MyAnimeList ID. Includes synopsis, genres, studios, ratings, and more.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mal_id": {"type": "integer", "description": "The MyAnimeList ID of the anime"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 8)", "default": 8}
                },
                "required": ["mal_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "anime_top",
            "description": "Get the top-rated or most popular anime on MyAnimeList. Can filter by type and category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max results (default 5, max 25)", "default": 5},
                    "type": {"type": "string", "description": "Filter by type: tv, movie, ova, special, ona, music", "default": ""},
                    "filter": {"type": "string", "description": "Filter category: airing, upcoming, bypopularity, favorite. Leave empty for all-time top.", "default": ""},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 8)", "default": 8}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "anime_seasonal",
            "description": "Get currently airing seasonal anime. Shows what's new this season with scores and synopses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max results (default 5, max 25)", "default": 5},
                    "filter": {"type": "string", "description": "Filter by type: tv, movie, ova, special, ona, music", "default": ""},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 8)", "default": 8}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manga_search",
            "description": "Search for manga on MyAnimeList by title. Returns matching manga with scores, volumes, chapters, and synopses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The manga title to search for (e.g. One Piece, Berserk)"},
                    "limit": {"type": "integer", "description": "Max results (default 5, max 25)", "default": 5},
                    "type": {"type": "string", "description": "Filter by type: manga, novel, lightnovel, oneshot, doujin, manhwa, manhua", "default": ""},
                    "status": {"type": "string", "description": "Filter by status: publishing, complete, hiatus, discontinued", "default": ""},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 8)", "default": 8}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "anime_random",
            "description": "Get a random anime from MyAnimeList. Great for discovery or recommendations.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wikipedia",
            "description": "Search and summarize Wikipedia articles. Searches for a query and returns the summary of the best matching article.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query to look up on Wikipedia"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "hackernews",
            "description": "Get top, new, or best stories from Hacker News. Returns titles, scores, authors, comment counts, and URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of stories to return (default 10, max 30)", "default": 10},
                    "type": {"type": "string", "description": "Story type: top, new, or best (default top)", "default": "top"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "yt_transcript",
            "description": "Get transcript of a YouTube video by video ID or full URL. Returns the text content of the transcript.",
            "parameters": {
                "type": "object",
                "properties": {
                    "video_id": {"type": "string", "description": "The YouTube video ID (e.g. dQw4w9WgXcQ) or full URL"}
                },
                "required": ["video_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "github_search",
            "description": "Search GitHub repositories by query. Returns repo names, descriptions, stars, languages, and URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query (e.g. 'machine learning' or 'lang:python')"},
                    "limit": {"type": "integer", "description": "Max results (default 5, max 10)", "default": 5}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "define_word",
            "description": "Get dictionary definition, phonetics, and examples for a word. Uses the free Dictionary API.",
            "parameters": {
                "type": "object",
                "properties": {
                    "word": {"type": "string", "description": "The word to define"}
                },
                "required": ["word"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "reddit_search",
            "description": "Search Reddit for posts matching a query. Optionally restrict to a specific subreddit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "limit": {"type": "integer", "description": "Max results (default 5, max 10)", "default": 5},
                    "subreddit": {"type": "string", "description": "Restrict search to a specific subreddit (e.g. python)", "default": ""}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "qr_encode",
            "description": "Generate a QR code image from text or URL. Saves to the screenshots directory and returns the file path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {"type": "string", "description": "Text or URL to encode in the QR code"}
                },
                "required": ["data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "uuid_gen",
            "description": "Generate UUIDs (version 4 random by default, or version 1 time-based).",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "Number of UUIDs to generate (default 1, max 10)", "default": 1},
                    "version": {"type": "integer", "description": "UUID version: 1 (time-based) or 4 (random, default)", "default": 4}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "hash_text",
            "description": "Hash text using common algorithms (md5, sha1, sha256, sha512). Returns the hex digest.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to hash"},
                    "algorithm": {"type": "string", "description": "Hash algorithm: md5, sha1, sha256, or sha512 (default sha256)", "default": "sha256"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ssl_check",
            "description": "Check SSL certificate details for a domain. Returns issuer, subject, expiry date, and days until expiry.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "The domain to check (e.g. example.com)"},
                    "port": {"type": "integer", "description": "Port number (default 443)", "default": 443}
                },
                "required": ["domain"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "http_headers",
            "description": "Check HTTP response headers for a URL. Sends a HEAD request and returns all response headers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL including protocol (e.g. https://example.com)"},
                    "follow_redirects": {"type": "boolean", "description": "Whether to follow redirects (default True)", "default": True}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "joke",
            "description": "Get a random joke from JokeAPI. Choose from categories like programming, general, pun, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Joke category: any, programming, misc, dark, pun, spooky, christmas (default any)", "default": "any"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "quote",
            "description": "Get a random inspirational quote. Optionally filter by tag (e.g. inspiration, wisdom).",
            "parameters": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "description": "Tag to filter by (e.g. inspiration, wisdom, love). Leave empty for random.", "default": ""}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lyrics",
            "description": "Get song lyrics by artist and title. Returns lyrics text truncated to 2000 characters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "artist": {"type": "string", "description": "Artist name (e.g. The Beatles)"},
                    "title": {"type": "string", "description": "Song title (e.g. Hey Jude)"}
                },
                "required": ["artist", "title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "color_picker",
            "description": "Convert between hex, RGB, and HSL color formats. Also suggests complementary colors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "color": {"type": "string", "description": "Color in hex (#ff0000), rgb(r,g,b), or hsl(h,s,l) format"}
                },
                "required": ["color"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "Get current weather for a city or coordinates. Returns temperature, humidity, wind, and conditions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name (e.g. Bangkok) or coordinates (e.g. 13.75,100.52)"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 8)", "default": 8}
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "exchange_rate",
            "description": "Get exchange rates for a currency. Shows rate against major world currencies or converts between two specific currencies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "base": {"type": "string", "description": "Base currency code (e.g. USD, EUR, THB). Default USD.", "default": "USD"},
                    "target": {"type": "string", "description": "Target currency to convert to (e.g. EUR). Leave empty to show all rates.", "default": ""},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 8)", "default": 8}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "country_info",
            "description": "Get detailed information about a country including capital, population, languages, currency, flag, and more.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Country name (e.g. Thailand, Japan, France)"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 8)", "default": 8}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tv_search",
            "description": "Search for TV shows and movies by title. Returns show info including status, genres, rating, network, and summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Show or movie title to search for (e.g. Breaking Bad)"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 8)", "default": 8}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Set a timer/reminder that will notify you after a specified duration. Use this for reminders, cooking timers, delayed notifications, or anything time-based. The bot will DM you when time is up.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration": {"type": "string", "description": "Duration string like '30 minutes', '5 seconds', '1 hour', '2 hours 30 minutes', '10 min'. Supports seconds, minutes, hours, days."},
                    "message": {"type": "string", "description": "What to remind you about when the timer fires"}
                },
                "required": ["duration", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_timer",
            "description": "Cancel a previously set timer by its ID. Use timer_list first to see your active timers and their IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timer_id": {"type": "string", "description": "The ID of the timer to cancel (e.g. timer_1700000000_1)"}
                },
                "required": ["timer_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "timer_list",
            "description": "List all active (unfired) timers for the current user. Shows each timer's ID, message, duration, and remaining time.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Ask the user a question. Use this INSTEAD of asking in plain text — it gives the user buttons to pick from or a text box to type their answer. Call this whenever you need the user to provide info, make a choice, or answer a question.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question to ask the user"},
                    "options": {"type": "array", "items": {"type": "string"}, "description": "Predefined answer options (buttons for Discord users)", "default": []}
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "publish_research",
            "description": "Publish research findings as a public web page. Use this AFTER completing significant research, analysis, or investigation to create a shareable website. Only use for research/analysis tasks — not for general chat. The page is accessible online and auto-expires after 7 days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of the research page"},
                    "content": {"type": "string", "description": "The research content in markdown format. Include sections, findings, data, code blocks, and citations as needed."},
                    "author": {"type": "string", "description": "Author name or attribution (default: Charlyn AI)", "default": "Charlyn AI"}
                },
                "required": ["title", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_publications",
            "description": "List all published research sites with their URLs and expiry dates.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "anime_download",
            "description": "Download an anime episode using ani-cli. Searches for and downloads the best match. Returns the file path of the downloaded video.",
            "parameters": {
                "type": "object",
                "properties": {
                    "anime_name": {"type": "string", "description": "Anime title or search term (e.g. 'One Piece episode 1070' or 'Attack on Titan')"}
                },
                "required": ["anime_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "video_upload",
            "description": "Upload a video file to the video streaming worker. Returns a watch URL that works with Discord's og-video embed. Videos over 30 minutes should be split first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the video file to upload"},
                    "title": {"type": "string", "description": "Display title for the video", "default": "Untitled"},
                    "part": {"type": "integer", "description": "Part number if this is part of a split video", "default": 1},
                    "total_parts": {"type": "integer", "description": "Total number of parts if split", "default": 1}
                },
                "required": ["file_path", "title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "charlyn_end_conversation",
            "description": "End the conversation immediately with the user. Use this when the user is violating your guidelines, being abusive, or if you determine the interaction should stop. The reason will be shown to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "The reason why you are ending the conversation"}
                },
                "required": ["reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "anime_download_and_upload",
            "description": "Download an anime episode using ani-cli and upload it to the video streaming worker in one step. Auto-detects if the video is longer than 30 minutes and splits it into parts. Returns streamable Discord-ready watch URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "anime_name": {"type": "string", "description": "Anime title or search term (e.g. 'One Piece episode 1070' or 'Demon Slayer movie')"}
                },
                "required": ["anime_name"]
            }
        }
    }
]
