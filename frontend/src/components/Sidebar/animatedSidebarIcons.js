import { createElement } from 'react';
import {
  BookOpenText as GuideIcon,
  ChevronDown as ChevronDownIcon,
  ChevronUp as ChevronUpIcon,
  CircleUserRound as ProfileIcon,
  FlaskConical as PharmacogeneticsIcon,
  House as HomeIcon,
  KeyRound as KeyIcon,
  LayoutGrid as CategoriesIcon,
  LogOut as LogoutIcon,
  Map as AncestryIcon,
  MessageCircle as ChatIcon,
  Settings as SettingsIcon,
  Stethoscope as DiseasesIcon,
  Upload as UploadIcon,
  UserRound as TraitsIcon,
  UserRoundX as RemoveAccountIcon,
} from '@animateicons/react/lucide';

const createBriefHoverIcon = (Icon) => {
  const BriefHoverIcon = (props) => createElement(Icon, { ...props, duration: 0.6 });
  BriefHoverIcon.displayName = `${Icon.displayName || 'AnimatedIcon'}BriefHover`;
  return BriefHoverIcon;
};

// Order of categoryItems matches RESULT_NAV_ITEMS (config/resultNav.js).
export const animatedSidebarIcons = {
  profile: createBriefHoverIcon(ProfileIcon),
  profileExpand: createBriefHoverIcon(ChevronDownIcon),
  profileCollapse: createBriefHoverIcon(ChevronUpIcon),
  key: createBriefHoverIcon(KeyIcon),
  removeAccount: createBriefHoverIcon(RemoveAccountIcon),
  categories: createBriefHoverIcon(CategoriesIcon),
  categoriesExpand: createBriefHoverIcon(ChevronDownIcon),
  categoriesCollapse: createBriefHoverIcon(ChevronUpIcon),
  categoryItems: [AncestryIcon, TraitsIcon, PharmacogeneticsIcon, DiseasesIcon, GuideIcon].map(createBriefHoverIcon),
  aiExpand: createBriefHoverIcon(ChevronDownIcon),
  aiCollapse: createBriefHoverIcon(ChevronUpIcon),
  chat: createBriefHoverIcon(ChatIcon),
  admin: createBriefHoverIcon(SettingsIcon),
  adminExpand: createBriefHoverIcon(ChevronDownIcon),
  adminCollapse: createBriefHoverIcon(ChevronUpIcon),
  upload: createBriefHoverIcon(UploadIcon),
  home: createBriefHoverIcon(HomeIcon),
  logout: createBriefHoverIcon(LogoutIcon),
};
