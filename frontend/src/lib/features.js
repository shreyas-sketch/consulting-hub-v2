// Feature keys (match backend plans.FEATURES) with the plain-English copy used on lock cards, the menu,
// "All tools" and "What's inside". `group` decides where the tool sits in the menu.

export const PLAN_LABEL = { free: "Free account", member: "₹1,999 plan", l1: "L1", l2: "L2 Mentorship" };
export const PLAN_RANK = { free: 0, member: 1, l1: 2, l2: 3 };

export const FEATURES = {
  // webinar tools
  readiness: { name: "Readiness Score", what: "Rate yourself on the six skills a consultant needs and see where to start.", plan: "free", to: "/app/readiness" },
  start: { name: "Starting Point", what: "Find your niche with the EDE framework and turn your income goal into weekly numbers.", plan: "free", to: "/app/start" },
  case: { name: "Weekly Case", what: "Solve a real business case, get a score out of 10 and see a model answer.", plan: "free", to: "/app/cases" },
  brief: { name: "Meeting Brief", what: "Before you meet a company, get a one-page brief: news, likely problems and questions to ask.", plan: "free", to: "/app/brief" },
  linkedin: { name: "LinkedIn Score", what: "Score your profile out of 100 and see the three things to fix first.", plan: "free", to: "/app/linkedin" },
  file: { name: "My Consulting File", what: "Everything you've made, on one page you can print or save as PDF.", plan: "free", to: "/app/file" },
  // ₹1,999 plan
  linkedin_improve: { name: "LinkedIn rewrites", what: "New headline options, an About section and post ideas written around your niche.", plan: "member", to: "/app/linkedin" },
  presentation: { name: "Presentation Builder", what: "Turn a case, a brief or your notes into a client-ready deck.", plan: "member", to: "/app/decks" },
  visuals: { name: "Visual Builder", what: "Frameworks, charts and mind maps for your slides and posts.", plan: "member", to: "/app/visuals" },
  website: { name: "Website Builder", what: "A consulting website with your offer and contact details, live on its own link.", plan: "member", to: "/app/website" },
  listen: { name: "Listen mode", what: "Hear the weekly case and your briefs as audio on the go.", plan: "member", to: "/app/listen" },
  doc_reader: { name: "Doc Reader", what: "Upload reports and documents, then ask questions about them.", plan: "member", to: "/app/docs" },
  progress: { name: "Progress Report", what: "A monthly report on how far you've come and what to work on next.", plan: "member", to: "/app/progress" },
  support: { name: "Support", what: "Ask the team anything about the tools, your plan or your payments.", plan: "member", to: "/app/support" },
  // L1
  program: { name: "4-3-2-1 action program", what: "The action program in your first month, with your coach.", plan: "l1", to: "/app/program" },
  calls: { name: "Group calls with Akshat", what: "Two live group calls a month.", plan: "l1", to: "/app/calls" },
  recordings: { name: "Recordings and workbooks", what: "Every session recording and workbook in one place.", plan: "l1", to: "/app/library" },
  recaps: { name: "Session Recap Pack", what: "After every session: summary, action points and an audio recap.", plan: "l1", to: "/app/recaps" },
  action_tools: { name: "Action Hub tools", what: "Akshat's 4-3-2-1 tools: niche, frameworks, pitch, LinkedIn blueprint and more.", plan: "l1", to: "/app/hub" },
  akshat_ai: { name: "Akshat AI", what: "Ask questions and get answers from Akshat's own sessions.", plan: "l1", to: "/app/akshat-ai" },
  offer_card: { name: "Offer Card", what: "Your one-page consulting offer: who you help, the result, the price.", plan: "l1", to: "/app/offer" },
  story_bank: { name: "Career Story Bank", what: "Record a story a week from your career and turn it into proof for clients.", plan: "l1", to: "/app/stories" },
  insight_pack: { name: "Industry Insight Pack", what: "A monthly pack on your industry, with an audio version.", plan: "l1", to: "/app/insights" },
  portfolio: { name: "Portfolio Project", what: "A project a month that becomes a case study and a short video.", plan: "l1", to: "/app/portfolio" },
  pitch: { name: "Pitch Practice", what: "Practise your pitch out loud and get feedback (English).", plan: "l1", to: "/app/pitch" },
  research: { name: "Research Notebook", what: "Collect sources on a topic and get summaries and answers from them.", plan: "l1", to: "/app/research" },
  // L2
  mentorship_tools: { name: "Mentorship tools", what: "Book Builder, Credibility Code, Document Builder, pricing and 30 more.", plan: "l2", to: "/app/mentorship" },
  network_finder: { name: "Warm Network Finder", what: "Find the people in your network most likely to need you.", plan: "l2", to: "/app/network" },
  outreach: { name: "Outreach Drafter", what: "Draft messages to your warm network. You send them.", plan: "l2", to: "/app/outreach" },
  radar: { name: "Opportunity Radar", what: "Companies in your niche showing signs they need help.", plan: "l2", to: "/app/radar" },
  call_prep: { name: "Discovery Call Prep", what: "Questions, likely problems and an agenda for your first client call.", plan: "l2", to: "/app/call-prep" },
  proposal: { name: "Proposal Follow-through", what: "Turn a discovery call into a proposal and follow it up.", plan: "l2", to: "/app/proposals" },
  client_diagnostic: { name: "Client Diagnostic", what: "A diagnostic your prospects fill in; you get the report.", plan: "l2", to: "/app/diagnostic" },
  social_builder: { name: "Social Media Builder", what: "Posts for your niche, 30 a month.", plan: "l2", to: "/app/social" },
  bootcamps: { name: "Bootcamps", what: "Build your practice step by step, with tasks the team reviews.", plan: "l2", to: "/app/bootcamps" },
};

export const featureInfo = (key) => FEATURES[key] || { name: "This tool", what: "", plan: "member" };

export const WEBINAR_TOOLS = ["readiness", "start", "case", "brief", "linkedin", "file"];

// Menu groups (AppShell). Keys must exist in FEATURES.
export const MENU_GROUPS = [
  { plan: "member", label: "₹1,999 plan", keys: ["presentation", "visuals", "website", "listen", "doc_reader", "progress"] },
  { plan: "l1", label: "L1", keys: ["program", "calls", "recordings", "recaps", "action_tools", "akshat_ai", "offer_card", "story_bank", "insight_pack", "portfolio", "pitch", "research"] },
  { plan: "l2", label: "L2 Mentorship", keys: ["mentorship_tools", "network_finder", "outreach", "radar", "call_prep", "proposal", "client_diagnostic", "social_builder", "bootcamps"] },
];
