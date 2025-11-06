export type ExecSummaryItem = {
  bullet: string;
  source?: string;
};

export type TimelineItem = {
  timestamp: string;
  event: string;
  evidence: string;
};

export type MitreItem = {
  action: string;
  ttpId: string;
  explanation: string;
};

export type AttackDetailItem = {
  artifact: string;
  bullet: string;
  raw: string;
};

export type IoCItem = {
  ioc: string;
  type: string;
  timestamp?: string;
  source: string;
  context?: string;
};

export type AdditionalNeededItem = {
  what: string;
  purpose: string;
  successCriteria: string;
};

export type ReportData = {
  title?: string;
  date?: string;
  version?: string;
  execSummary: ExecSummaryItem[];    
  timeline: TimelineItem[];
  mitre: MitreItem[];
  attackDetails: AttackDetailItem[];
  iocs: IoCItem[];
  additionalNeeded: AdditionalNeededItem[];
  rawAppendix?: string;
};