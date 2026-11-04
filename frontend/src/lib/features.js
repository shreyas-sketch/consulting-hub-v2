// Feature keys (match backend plans.FEATURES) with the plain-English copy used on lock cards, the menu and "What's inside".
// stage: 1 = live now; 2–4 = being built (shown as "Coming soon").

export const PLAN_LABEL = { free: "Free account", member: "₹1,999 plan", l1: "L1", l2: "L2 Mentorship" };
export const PLAN_RANK = { free: 0, member: 1, l1: 2, l2: 3 };

export const FEATURES = {
  readiness: { name: "Readiness Score", what: "Rate yourself on the six skills a consultant needs and see where to start.", plan: "free", stage: 1, to: "/app/readiness" },
  start: { name: "Starting Point", what: "Find your niche with the EDE framework and turn your income goal into weekly numbers.", plan: "free", stage: 1, to: "/app/start" },
  case: { name: "Weekly Case", what: "Solve a real business case, get a score out of 10 and see a model answer.", plan: "free", stage: 1, to: "/app/cases" },
  brief: { name: "Meeting Brief", what: "Before you meet a company, get a one-page brief: news, likely problems and questions to ask.", plan: "free", stage: 1, to: "/app/brief" },
  linkedin: { name: "LinkedIn Score", what: "Score your profile out of 100 and see the three things to fix first.", plan: "free", stage: 1, to: "/app/linkedin" },
  file: { name: "My Consulting File", what: "Everything you've made, on one page you can print or save as PDF.", plan: "free", stage: 1, to: "/app/file" },
  linkedin_improve: { name: "LinkedIn rewrites", what: "New headline options and an About section written around your niche.", plan: "member", stage: 1, to: "/app/linkedin" },
  presentation: { name: "Presentation Builder", what: "Turn your work on a case into a client-ready deck.", plan: "member", stage: 2 },
  visuals: { name: "Visual Builder", what: "Charts, frameworks and mind maps for your slides and posts.", plan: "member", stage: 2 },
  website: { name: "Website Builder", what: "A one-page consulting website with your offer and contact details.", plan: "member", stage: 2 },
  listen: { name: "Listen mode", what: "Hear the weekly case and your briefs as audio on the go.", plan: "member", stage: 2 },
  doc_reader: { name: "Doc Reader", what: "Upload reports and documents, then ask questions about them.", plan: "member", stage: 2 },
  progress: { name: "Progress Report", what: "A monthly report on how far you've come.", plan: "member", stage: 2 },
  action_tools: { name: "Action Hub tools", what: "The 4-3-2-1 action program tools: frameworks, offers, pricing and more.", plan: "l1", stage: 3 },
  calls: { name: "Group calls with Akshat", what: "Two live group calls a month.", plan: "l1", stage: 3 },
  recordings: { name: "Recordings and workbooks", what: "Every session recording and workbook in one place.", plan: "l1", stage: 3 },
  offer_card: { name: "Offer Card", what: "Your one-page consulting offer: who you help, the result, the price.", plan: "l1", stage: 3 },
  story_bank: { name: "Career Story Bank", what: "Record a story a week from your career and turn it into proof for clients.", plan: "l1", stage: 3 },
  insight_pack: { name: "Industry Insight Pack", what: "A monthly pack on your industry, with an audio version.", plan: "l1", stage: 3 },
  portfolio: { name: "Portfolio Project", what: "A monthly project that becomes a case study and a short video.", plan: "l1", stage: 3 },
  akshat_ai: { name: "Akshat AI", what: "Ask questions and get answers from Akshat's own sessions.", plan: "l1", stage: 3 },
  pitch: { name: "Pitch Practice", what: "Practise your pitch out loud and get feedback (English).", plan: "l1", stage: 3 },
  research: { name: "Research Notebook", what: "Collect sources on a topic and get summaries and answers from them.", plan: "l1", stage: 3 },
  recaps: { name: "Session Recap Pack", what: "After every session: summary, action points and audio recap.", plan: "l1", stage: 3 },
  network_finder: { name: "Warm Network Finder", what: "Find the people in your network most likely to need you.", plan: "l2", stage: 4 },
  outreach: { name: "Outreach Drafter", what: "Draft messages to your warm network. You send them.", plan: "l2", stage: 4 },
  radar: { name: "Opportunity Radar", what: "Companies in your niche showing signs they need help.", plan: "l2", stage: 4 },
  call_prep: { name: "Discovery Call Prep", what: "Questions, likely problems and an agenda for your first client call.", plan: "l2", stage: 4 },
  proposal: { name: "Proposal Follow-through", what: "Turn a discovery call into a proposal and follow it up.", plan: "l2", stage: 4 },
  client_diagnostic: { name: "Client Diagnostic", what: "A structured diagnosis of a client's business.", plan: "l2", stage: 4 },
  social_builder: { name: "Social Media Builder", what: "Posts for your niche, 30 a month.", plan: "l2", stage: 4 },
};

export const featureInfo = (key) => FEATURES[key] || { name: "This tool", what: "", plan: "member", stage: 1 };

export const WEBINAR_TOOLS = ["readiness", "start", "case", "brief", "linkedin", "file"];
