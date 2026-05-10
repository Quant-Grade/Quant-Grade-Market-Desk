from .schemas import OperatorProfile, OperatorError

def validate_profile(profile_str: str) -> OperatorProfile:
    if not OperatorProfile.has_value(profile_str):
        valid_profiles = [p.value for p in OperatorProfile]
        raise OperatorError(f"Unknown profile: {profile_str}. Valid profiles are: {valid_profiles}")
    
    return OperatorProfile(profile_str)
