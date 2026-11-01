// Headings for the interest chips in onboarding step 3 (spec 25.1). Topics come from the frozen
// taxonomy; any topic not listed here still appears, under "Other".
import TAXONOMY from '../../data/taxonomy/topics.json'

const GROUPS = [
  ['Theory and mathematics', ['algorithms', 'complexity theory', 'computability', 'randomized algorithms',
    'optimization', 'linear algebra', 'probability', 'statistics', 'discrete mathematics', 'game theory', 'quantum computing']],
  ['AI and data', ['machine learning', 'deep learning', 'reinforcement learning', 'natural language processing',
    'computer vision', 'image processing', 'speech processing', 'pattern recognition', 'intelligent agents',
    'data mining', 'information retrieval', 'data visualization', 'databases', 'big data']],
  ['Systems and hardware', ['operating systems', 'computer architecture', 'parallel computing', 'distributed systems',
    'cloud computing', 'computer networks', 'wireless systems', 'high performance computing', 'embedded systems',
    'hardware verification', 'signal processing']],
  ['Software', ['software engineering', 'programming languages', 'compilers', 'formal methods']],
  ['Security', ['security', 'cryptography', 'privacy', 'network security', 'digital forensics']],
  ['People, graphics and robots', ['human computer interaction', 'user interfaces', 'accessibility', 'virtual reality',
    'computer graphics', 'geometric modeling', 'computational geometry', 'robotics', 'autonomous systems', 'control systems']],
  ['Science', ['computational biology', 'bioinformatics', 'scientific computing']],
]

const listed = new Set(GROUPS.flatMap(([, topics]) => topics))
const other = TAXONOMY.filter((t) => !listed.has(t))

export const TOPIC_GROUPS = [
  ...GROUPS.map(([heading, topics]) => [heading, topics.filter((t) => TAXONOMY.includes(t))]),
  ...(other.length ? [['Other', other]] : []),
]
